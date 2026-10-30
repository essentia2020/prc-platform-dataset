"""Stage ``extract_sciety_evaluations``: docmaps per Sciety group.

Retrieval unit: one paginated walk per ``evaluations__<group_slug>``
scope using the per-publisher index documented at
https://sciety.org/docmaps/v1/ (``index?publisheraccount=<group page URL>``).
Every docmap in the response is checked against the group's account
identity (slug URL or configured group id); a mismatch hard-fails
normalisation. No foreign docmap is silently discarded.

Flattening (§4.3 of the data dictionary): one line per evaluation output in
docmap order; ``evaluation_index`` is the position of the output within the
docmap, ``evaluation_id`` is ``sciety:<docmap_id>:<index>`` unless the
output carries a DOI.  Complete walks only.

Coverage probe (D-058): the index lists only the groups Sciety has enabled
for docmaps, so an empty per-group response is ambiguous on its own.  In
``per_group`` mode the stage also walks the unfiltered index once per run as
scope ``index__all`` (reused like any other complete walk) and records, for
every group scope, whether the group is present in that snapshot and with how
many docmaps (``index_coverage`` in the run manifest; the snapshot itself
under ``sciety_index_snapshot``).  In ``full_index`` mode the single
full-index walk serves as the snapshot.  The probe never changes a walk
state or a count; the analysis stage reads it to tell a source that does
not cover a group (``source_not_covering``) from a selector that matched
nothing (``selector_no_match``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urljoin, urlsplit, parse_qs, urlencode, urlunsplit

from ..common.config import RunConfig
from ..common.dates import DateError, format_partial_date, parse_partial_date
from ..common.identifiers import normalise_doi
from ..common.interim import SCIETY_EVALUATION_COLUMNS, resolve_interim_root, write_csv
from ..common.manifest import (DEFAULT_MANIFEST_ROOT, WalkRecord, list_walks, run_manifest_path,
                               update_run_manifest_field, update_run_manifest_scope, select_walk)
from ..common.raw_store import RawStore
from ..common.walk import CursorWalker, ParsedPage
from .crossref_common import ExtractionIncomplete, http_settings
from ..common.http import PoliteClient, default_transport
from .selectors import ScietyScope, sciety_scopes
from ..normalise.sciety_integrity import validate_docmap_publishers

SOURCE = "sciety"
INDEX_SCOPE = "index__all"                 # unfiltered docmaps index, one walk per run (D-058)
FULL_INDEX_SCOPE = "evaluations__full_index"
IN_INDEX, NOT_IN_INDEX, UNVERIFIED = "in_index", "not_in_index", "unverified"


@dataclass
class ScietyOutcome:
    scope: ScietyScope
    walk: WalkRecord
    rows_written: int = 0
    foreign_docmaps: int = 0
    issues: list[str] = field(default_factory=list)
    index_coverage: dict[str, Any] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.walk.is_complete


def build_client(run_config: RunConfig, sources_config: Mapping[str, Any], *, transport=None,
                 sleeper=None, logger=None) -> PoliteClient:
    settings = http_settings(run_config, sources_config, SOURCE)
    rate = sources_config["sources"][SOURCE].get("rate_limit") or {}
    per_second = float(rate.get("max_requests_per_second") or 1)
    kwargs: dict[str, Any] = dict(
        user_agent=run_config.user_agent(), timeout_seconds=float(settings["timeout_seconds"]),
        max_attempts_per_page=int(settings["max_attempts_per_page"]),
        backoff_seconds=[float(b) for b in settings["backoff_seconds"]],
        min_interval_seconds=1.0 / per_second if per_second > 0 else 1.0,
        accept=str(settings["accept"]), transport=transport or default_transport, logger=logger)
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    return PoliteClient(**kwargs)


def index_url(sources_config: Mapping[str, Any], scope: ScietyScope) -> str:
    source = sources_config["sources"][SOURCE]
    template = source["query_templates"]["docmaps_by_publisher"].strip()
    return source["base_url"].rstrip("/") + template.format(group_id=quote(scope.publisher_account_url, safe=""))


def full_index_url(sources_config: Mapping[str, Any]) -> str:
    source = sources_config["sources"][SOURCE]
    return source["base_url"].rstrip("/") + source["query_templates"]["docmaps_index"].strip()


def docmap_account_id(docmap: Mapping[str, Any]) -> str:
    return str(((docmap.get("publisher") or {}).get("account") or {}).get("id", "")).rstrip("/")


def index_coverage_counts(store: RawStore, walk: WalkRecord, scopes: list[ScietyScope]
                          ) -> tuple[dict[str, int], dict[str, int]]:
    """Docmaps per group scope and per publisher account in a complete index walk.

    The first mapping is keyed by ``scope_id`` and uses the register's account
    matching (slug URL or configured group id); the second is keyed by the
    account id as served and lists every group the snapshot carries, named or
    not in the register.
    """
    if not walk.is_complete:
        raise ExtractionIncomplete(f"index walk {walk.walk_id} is {walk.state}")
    by_scope = {scope.scope_id: 0 for scope in scopes}
    by_account: dict[str, int] = {}
    for page in walk.pages:
        payload = store.read_response_json(page.response_path)
        for docmap in payload["articles"]:
            account = docmap_account_id(docmap)
            by_account[account] = by_account.get(account, 0) + 1
            for scope in scopes:
                if scope.account_matches(account):
                    by_scope[scope.scope_id] += 1
    return by_scope, by_account


def coverage_entry(scope: ScietyScope, index_walk: WalkRecord | None, by_scope: Mapping[str, int] | None,
                   docmaps_walked: int | None) -> dict[str, Any]:
    """``index_coverage`` record of one group scope for the run manifest."""
    if index_walk is None or by_scope is None:
        return {"status": UNVERIFIED, "docmaps_in_index": None, "docmaps_walked": docmaps_walked,
                "index_walk_id": index_walk.walk_id if index_walk is not None else None,
                "index_retrieved_at": None}
    n = int(by_scope.get(scope.scope_id, 0))
    return {"status": IN_INDEX if n > 0 else NOT_IN_INDEX, "docmaps_in_index": n,
            "docmaps_walked": docmaps_walked, "index_walk_id": index_walk.walk_id,
            "index_retrieved_at": index_walk.ended_at_utc}


def parse_index_page(body: bytes, next_paths=("next", "links.next")) -> ParsedPage:
    payload = json.loads(body.decode("utf-8"))
    articles = payload.get("articles") if isinstance(payload, Mapping) else None
    if not isinstance(articles, list):
        raise ValueError("Sciety page must contain an articles array")
    continuations = []
    for path in next_paths:
        value = payload
        for key in path.split("."):
            value = value.get(key) if isinstance(value, Mapping) else None
        if value is None:
            continue
        if isinstance(value, Mapping):
            value = value.get("href")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid Sciety continuation")
        continuations.append(value)
    if len(set(continuations)) > 1:
        raise ValueError("conflicting Sciety continuation links")
    if payload.get("has_more") is True and not continuations:
        raise ValueError("Sciety reports more pages without a continuation")
    nxt = continuations[0] if continuations else None
    return ParsedPage(len(articles), nxt, terminal=nxt is None)


def continuation_url(initial_url: str, continuation: str, scope: ScietyScope | None) -> str:
    """Keep the publisher filter on every page; reject host or group changes."""
    resolved = urlsplit(urljoin(initial_url, continuation or initial_url))
    base = urlsplit(initial_url)
    if (resolved.scheme, resolved.netloc, resolved.path) != (base.scheme, base.netloc, base.path):
        raise ValueError("Sciety continuation changes endpoint")
    query = parse_qs(resolved.query, keep_blank_values=True)
    accounts = query.get("publisheraccount")
    if scope is None and accounts is not None:
        raise ValueError("full-index continuation introduces a publisher filter")
    if scope and accounts is not None and accounts != [scope.publisher_account_url]:
        raise ValueError("Sciety continuation changes publisheraccount")
    if scope:
        query["publisheraccount"] = [scope.publisher_account_url]
    return urlunsplit((resolved.scheme, resolved.netloc, resolved.path,
                       urlencode(query, doseq=True), ""))


# -------------------------------------------------------------- docmap walk
def iter_steps(docmap: Mapping[str, Any]):
    """Yield steps in ``first-step`` / ``next-step`` order (loops are cut)."""
    steps = docmap.get("steps") or {}
    key = docmap.get("first-step")
    seen: set[str] = set()
    while key and key in steps and key not in seen:
        seen.add(key)
        step = steps[key]
        yield key, step
        key = step.get("next-step")
    # Steps unreachable from first-step are appended in key order.
    for key in sorted(k for k in steps if k not in seen):
        yield key, steps[key]


def _output_urls(output: Mapping[str, Any]) -> list[str]:
    urls = []
    if output.get("url"):
        urls.append(str(output["url"]))
    for content in output.get("content") or []:
        if isinstance(content, Mapping) and content.get("url"):
            urls.append(str(content["url"]))
    return urls


def flatten_docmap(docmap: Mapping[str, Any], *, platform_id: str, walk: WalkRecord, page_no: int,
                   accepted_attempt: int, retrieved_at_utc: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows for one docmap plus a list of issues (never raised)."""
    issues: list[str] = []
    publisher = docmap.get("publisher") or {}
    account = publisher.get("account") or {}
    docmap_id = str(docmap.get("id", ""))
    rows: list[dict[str, Any]] = []
    index = 0
    for _, step in iter_steps(docmap):
        inputs = [i for i in (step.get("inputs") or []) if isinstance(i, Mapping)]
        input_dois = []
        for item in inputs:
            raw = item.get("doi") or ""
            if raw:
                try:
                    input_dois.append(normalise_doi(str(raw)))
                except Exception:
                    issues.append(f"{docmap_id}: malformed input DOI {raw!r}")
        for action in step.get("actions") or []:
            for output in (action.get("outputs") or []) if isinstance(action, Mapping) else []:
                if not isinstance(output, Mapping):
                    continue
                published = output.get("published")
                try:
                    date_text = format_partial_date(parse_partial_date(published))
                except DateError:
                    date_text = ""
                    issues.append(f"{docmap_id}: unparseable published value {published!r}")
                urls = _output_urls(output)
                evaluation_doi = ""
                if output.get("doi"):
                    try:
                        evaluation_doi = normalise_doi(str(output["doi"]))
                    except Exception:
                        issues.append(f"{docmap_id}: malformed evaluation DOI {output.get('doi')!r}")
                evaluation_id = evaluation_doi if evaluation_doi else f"sciety:{docmap_id}:{index}"
                for work_doi in input_dois or [""]:
                    rows.append({
                        "group_id": str(account.get("id", "")),
                        "group_name": str(publisher.get("name", "")),
                        "docmap_id": docmap_id,
                        "evaluation_index": index,
                        "evaluated_work_doi": work_doi,
                        "evaluation_id": evaluation_id,
                        "evaluation_url": urls[0] if urls else "",
                        "evaluation_doi": evaluation_doi,
                        "evaluation_date": date_text,
                        "evaluation_type": str(output.get("type", "")),
                        "retrieved_at_utc": retrieved_at_utc,
                        "platform_id": platform_id,
                        "walk_id": walk.walk_id,
                        "page": page_no,
                        "accepted_attempt": accepted_attempt,
                    })
                if not input_dois:
                    issues.append(f"{docmap_id}: evaluation {index} has no input DOI")
                index += 1
    return rows, issues


def flatten_walk(store: RawStore, walk: WalkRecord, scope: ScietyScope, *,
                 full_index: bool = False) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not walk.is_complete:
        raise ExtractionIncomplete(f"walk {walk.walk_id} of scope {walk.scope} is {walk.state}")
    rows: list[dict[str, Any]] = []
    foreign = 0
    issues: list[str] = []
    for page in walk.pages:
        payload = store.read_response_json(page.response_path)
        docmaps = payload["articles"]
        if full_index:
            # Explicitly configured full-index fallback: partition, then validate.
            # The full unpartitioned response remains in the immutable raw store.
            partition = [d for d in docmaps if scope.account_matches(
                str(((d.get("publisher") or {}).get("account") or {}).get("id", "")))]
            foreign += len(docmaps) - len(partition)
            docmaps = partition
        validate_docmap_publishers(docmaps, scope)
        for docmap in docmaps:
            new_rows, new_issues = flatten_docmap(docmap, platform_id=scope.row_id, walk=walk, page_no=page.page,
                                                  accepted_attempt=page.accepted_attempt,
                                                  retrieved_at_utc=page.accepted_at_utc)
            rows.extend(new_rows)
            issues.extend(new_issues)
    return rows, foreign, issues


# ------------------------------------------------------------------- driver
def run(run_config: RunConfig, sources_config: Mapping[str, Any], platforms: list[Mapping[str, Any]], logger,
        *, raw_root=None, manifest_root: Path | None = None, interim_root=None, transport=None, sleeper=None,
        force_new_walk: bool = False) -> list[ScietyOutcome]:
    scopes = sciety_scopes(platforms)
    store = RawStore(raw_root)
    manifest_root = Path(manifest_root) if manifest_root else DEFAULT_MANIFEST_ROOT
    interim = resolve_interim_root(interim_root)
    client = build_client(run_config, sources_config, transport=transport, sleeper=sleeper, logger=logger)
    source_config = sources_config["sources"][SOURCE]
    mode = source_config.get("retrieval_mode", "per_group")
    if mode not in ("per_group", "full_index"):
        raise ValueError("unknown Sciety retrieval_mode")
    next_paths = source_config["pagination"]["next_paths"]
    manifest_path = run_manifest_path(manifest_root, run_config.run_id)
    manifest_kwargs = dict(run_id=run_config.run_id, cutoff=run_config.analysis_cutoff_date.isoformat(),
                           policy=run_config.selected_walk_policy, source=SOURCE)

    def walk_scope(scope_name: str, build_url, force: bool) -> tuple[WalkRecord, list[WalkRecord]]:
        walker = CursorWalker(client=client, store=store, manifest_root=manifest_root, run_id=run_config.run_id,
                              source=SOURCE, scope=scope_name, logger=logger)
        walk = walker.run(build_url=build_url, parse_page=lambda body: parse_index_page(body, next_paths),
                          initial_cursor="", force_new_walk=force)
        walks = list_walks(manifest_root, run_config.run_id, SOURCE, scope_name)
        selected, _ = select_walk(walks, run_config.selected_walk_policy)
        return (selected if selected is not None else walk), walks

    # Coverage probe (D-058): the unfiltered index, one walk per run.  In
    # full_index mode the data walk itself is the snapshot.
    index_scope = INDEX_SCOPE if mode == "per_group" else FULL_INDEX_SCOPE
    index_url_all = full_index_url(sources_config)
    index_walk, index_walks = walk_scope(index_scope, lambda cursor: continuation_url(index_url_all, cursor, None),
                                         force_new_walk)
    update_run_manifest_scope(manifest_path, scope=index_scope, walks=index_walks, **manifest_kwargs,
                              extra={"role": "coverage_probe"})
    by_scope: dict[str, int] | None = None
    if index_walk.is_complete:
        by_scope, by_account = index_coverage_counts(store, index_walk, scopes)
        update_run_manifest_field(manifest_path, run_id=run_config.run_id, key="sciety_index_snapshot", value={
            "scope": index_scope, "walk_id": index_walk.walk_id, "retrieved_at": index_walk.ended_at_utc,
            "pages": len(index_walk.pages), "docmaps_total": index_walk.items_total,
            "page_sha256": [p.sha256 for p in index_walk.pages],
            "groups": dict(sorted(by_account.items()))})
        if logger is not None:
            logger.event("sciety_index_snapshot", scope=index_scope, walk_id=index_walk.walk_id,
                         docmaps=index_walk.items_total, groups=len(by_account))
    elif logger is not None:
        logger.event("sciety_index_unverified", scope=index_scope, walk_state=index_walk.state)

    outcomes: list[ScietyOutcome] = []
    for scope in scopes:
        if mode == "per_group":
            url = index_url(sources_config, scope)
            walk, walks = walk_scope(scope.scope_id, lambda cursor, u=url, sc=scope: continuation_url(u, cursor, sc),
                                     force_new_walk)
            scope_name = scope.scope_id
        else:
            walk, walks, scope_name = index_walk, index_walks, FULL_INDEX_SCOPE
        outcome = ScietyOutcome(scope=scope, walk=walk)
        docmaps_walked: int | None = None
        if walk.is_complete:
            rows, foreign, issues = flatten_walk(store, walk, scope, full_index=mode == "full_index")
            outcome.foreign_docmaps = foreign
            outcome.issues = issues
            docmaps_walked = walk.items_total - foreign
            outcome.rows_written = write_csv(interim / f"sciety_evaluations__{scope.group_slug}.csv",
                                             SCIETY_EVALUATION_COLUMNS, rows)
            if logger is not None:
                logger.event("scope_flattened", source=SOURCE, scope=scope.scope_id, rows=outcome.rows_written,
                             foreign_docmaps=foreign, issues=len(issues))
        elif logger is not None:
            logger.event("scope_blocked", source=SOURCE, scope=scope.scope_id, walk_state=walk.state,
                         blocked_rows=[scope.row_id])
        outcome.index_coverage = coverage_entry(scope, index_walk, by_scope, docmaps_walked)
        if mode == "per_group":
            update_run_manifest_scope(manifest_path, scope=scope_name, walks=walks, **manifest_kwargs,
                                      extra={"index_coverage": outcome.index_coverage})
        else:
            # one shared walk: the scope entry is the probe entry; coverage per group is
            # kept in the snapshot record (groups) and in the outcome.
            update_run_manifest_scope(manifest_path, scope=scope_name, walks=walks, **manifest_kwargs,
                                      extra={"role": "coverage_probe"})
        outcomes.append(outcome)
    incomplete = [o for o in outcomes if not o.complete]
    problems = []
    if incomplete:
        detail = "; ".join(f"{o.scope.scope_id}: {o.walk.state} (blocks {o.scope.row_id})" for o in incomplete)
        problems.append(f"{len(incomplete)} Sciety scope(s) not complete — {detail}")
    if not index_walk.is_complete:
        problems.append(f"{index_scope}: {index_walk.state} (coverage of zero-item groups unverified)")
    if problems:
        raise ExtractionIncomplete("; ".join(problems))
    return outcomes
