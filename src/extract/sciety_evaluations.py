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
                               update_run_manifest_scope, select_walk)
from ..common.raw_store import RawStore
from ..common.walk import CursorWalker, ParsedPage
from .crossref_common import ExtractionIncomplete, http_settings
from ..common.http import PoliteClient, default_transport
from .selectors import ScietyScope, sciety_scopes
from ..normalise.sciety_integrity import validate_docmap_publishers

SOURCE = "sciety"


@dataclass
class ScietyOutcome:
    scope: ScietyScope
    walk: WalkRecord
    rows_written: int = 0
    foreign_docmaps: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.walk.is_complete


def build_client(run_config: RunConfig, sources_config: Mapping[str, Any], *, transport=None,
                 sleeper=None, logger=None) -> PoliteClient:
    settings = http_settings(run_config, sources_config)
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
    outcomes: list[ScietyOutcome] = []
    for scope in scopes:
        scope_name = scope.scope_id if mode == "per_group" else "evaluations__full_index"
        walker = CursorWalker(client=client, store=store, manifest_root=manifest_root, run_id=run_config.run_id,
                              source=SOURCE, scope=scope_name, logger=logger)
        url = (index_url(sources_config, scope) if mode == "per_group" else
               source_config["base_url"].rstrip("/") + source_config["query_templates"]["docmaps_index"])
        next_paths = sources_config["sources"][SOURCE]["pagination"]["next_paths"]
        walk = walker.run(build_url=lambda cursor: continuation_url(url, cursor, scope if mode == "per_group" else None),
                          parse_page=lambda body: parse_index_page(body, next_paths),
                          initial_cursor="", force_new_walk=force_new_walk and (mode == "per_group" or not outcomes))
        walks = list_walks(manifest_root, run_config.run_id, SOURCE, scope_name)
        selected, _ = select_walk(walks, run_config.selected_walk_policy)
        if selected is not None:
            walk = selected
        update_run_manifest_scope(run_manifest_path(manifest_root, run_config.run_id), run_id=run_config.run_id,
                                  cutoff=run_config.analysis_cutoff_date.isoformat(),
                                  policy=run_config.selected_walk_policy, source=SOURCE,
                                  scope=scope_name, walks=walks)
        outcome = ScietyOutcome(scope=scope, walk=walk)
        if walk.is_complete:
            rows, foreign, issues = flatten_walk(store, walk, scope, full_index=mode == "full_index")
            outcome.foreign_docmaps = foreign
            outcome.issues = issues
            outcome.rows_written = write_csv(interim / f"sciety_evaluations__{scope.group_slug}.csv",
                                             SCIETY_EVALUATION_COLUMNS, rows)
            if logger is not None:
                logger.event("scope_flattened", source=SOURCE, scope=scope.scope_id, rows=outcome.rows_written,
                             foreign_docmaps=foreign, issues=len(issues))
        elif logger is not None:
            logger.event("scope_blocked", source=SOURCE, scope=scope.scope_id, walk_state=walk.state,
                         blocked_rows=[scope.row_id])
        outcomes.append(outcome)
    incomplete = [o for o in outcomes if not o.complete]
    if incomplete:
        detail = "; ".join(f"{o.scope.scope_id}: {o.walk.state} (blocks {o.scope.row_id})" for o in incomplete)
        raise ExtractionIncomplete(f"{len(incomplete)} Sciety scope(s) not complete — {detail}")
    return outcomes
