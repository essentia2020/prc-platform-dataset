"""Shared machinery for the two Crossref extraction stages.

Retrieval unit: one cursor walk per scope ``works__<prefix>__<type>`` or
``works__issn_<issn>__<type>``.
Flattening unit: one interim CSV per register row, produced only from a
complete walk.  Nothing here aggregates or counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, parse_qs, urlsplit

from ..common.config import RunConfig
from ..common.dates import format_partial_date, parse_crossref_date, parse_timestamp
from ..common.http import PoliteClient, default_transport
from ..common.identifiers import collapse_repeated_slashes, identifier_flag, normalise_doi
from ..common.interim import (CROSSREF_REVIEW_COLUMNS, CROSSREF_WORK_COLUMNS, resolve_interim_root,
                              write_csv)
from ..common.manifest import (DEFAULT_MANIFEST_ROOT, WalkRecord, list_walks, run_manifest_path,
                               update_run_manifest_scope, select_walk, load_run_manifest, write_run_manifest)
from ..common.raw_store import RawStore
from ..common.walk import CursorWalker, ParsedPage
from ..common.windowed_walk import WindowedWalker
from ..common.windows import DateWindow, WindowError, date_windows, window_scope_id
from .selectors import (REVIEW_RECORD_TYPE, CrossrefScope, CrossrefSelector, crossref_scopes,
                        crossref_selectors, review_targets)

SOURCE = "crossref"


class ExtractionIncomplete(RuntimeError):
    """Raised after all scopes were attempted when at least one is not complete."""


@dataclass
class ScopeOutcome:
    scope: CrossrefScope
    walk: WalkRecord
    rows_written: dict[str, int] = field(default_factory=dict)
    blocked_rows: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.walk.is_complete


# ---------------------------------------------------------------- requests
def http_settings(run_config: RunConfig, sources_config: Mapping[str, Any]) -> dict[str, Any]:
    defaults = dict(sources_config.get("http_defaults") or {})
    overrides = dict((run_config.extra or {}).get("http") or {})
    merged = {**defaults, **overrides}
    merged.setdefault("timeout_seconds", 60)
    merged.setdefault("max_attempts_per_page", 5)
    merged.setdefault("backoff_seconds", [2, 5, 15, 45, 120])
    merged.setdefault("accept", "application/json")
    return merged


def build_client(run_config: RunConfig, sources_config: Mapping[str, Any], *, transport=None,
                 sleeper=None, logger=None) -> PoliteClient:
    settings = http_settings(run_config, sources_config)
    source = sources_config["sources"][SOURCE]
    rate = source.get("rate_limit") or {}
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


def scope_tolerance(pagination: Mapping[str, Any], scope_id: str) -> tuple[int, str]:
    """``(total_tolerance, tolerance_reason)`` for one scope.

    The source-wide values apply unless ``total_tolerance_overrides`` names
    the scope; an override must carry its own ``reason``.  Both values are
    written to the walk manifest's completion block, so a tolerated
    difference is always visible next to the totals it tolerated.
    """
    overrides = pagination.get("total_tolerance_overrides") or {}
    if scope_id in overrides:
        entry = overrides[scope_id] or {}
        if not isinstance(entry, Mapping) or "total_tolerance" not in entry:
            raise ExtractionIncomplete(f"total_tolerance_overrides[{scope_id}] needs total_tolerance and reason")
        return int(entry["total_tolerance"]), str(entry.get("reason") or "")
    return int(pagination.get("total_tolerance", 0) or 0), str(pagination.get("tolerance_reason") or "")


def windowed_scope_config(pagination: Mapping[str, Any], scope_id: str) -> Mapping[str, Any] | None:
    """The ``windowed_scopes`` entry of a scope (D-045 option c), or ``None``.

    A windowed scope is walked per date window at tolerance 0, so it may not
    also appear in ``total_tolerance_overrides``: the two mechanisms answer
    the same symptom in incompatible ways and the configuration must say
    which one applies.
    """
    windowed = pagination.get("windowed_scopes") or {}
    if scope_id not in windowed:
        return None
    entry = windowed[scope_id] or {}
    if not isinstance(entry, Mapping) or not {"date_field", "granularity", "first_window_start"} <= set(entry):
        raise ExtractionIncomplete(f"windowed_scopes[{scope_id}] needs date_field, granularity, "
                                   "first_window_start and reason")
    if not str(entry.get("reason") or "").strip():
        raise ExtractionIncomplete(f"windowed_scopes[{scope_id}] needs a reason")
    if scope_id in (pagination.get("total_tolerance_overrides") or {}):
        raise ExtractionIncomplete(f"{scope_id} is listed in both windowed_scopes and total_tolerance_overrides; "
                                   "a windowed scope is always checked at tolerance 0")
    return entry


def scope_windows(run_config: RunConfig, entry: Mapping[str, Any]) -> list[DateWindow]:
    """Window set of a windowed scope: guard + calendar periods through the cutoff + guard."""
    first = entry["first_window_start"]
    first = first if isinstance(first, date) else date.fromisoformat(str(first))
    try:
        return date_windows(str(entry["date_field"]), str(entry["granularity"]), first,
                            run_config.analysis_cutoff_date)
    except WindowError as exc:
        raise ExtractionIncomplete(f"windowed_scopes: {exc}") from exc


def _finish_url(base: str, path: str, select: list[str]) -> str:
    if select:
        path += "&select=" + ",".join(select)
    if "sort" in parse_qs(urlsplit(path).query):
        raise ValueError("sort is not allowed with Crossref cursor pagination")
    return base + path


def url_builder(run_config: RunConfig, sources_config: Mapping[str, Any], scope: CrossrefScope,
                window: DateWindow | None = None) -> Callable[[str], str]:
    """Page-URL builder for a scope; with ``window`` the window filter is added to the query."""
    source = sources_config["sources"][SOURCE]
    templates = source["query_templates"]
    if window is not None:
        if scope.kind == "issn":
            raise ExtractionIncomplete("windowed walks are defined for prefix scopes only")
        template_key = "works_by_prefix_type_and_window"
    else:
        template_key = "works_by_issn_and_type" if scope.kind == "issn" else "works_by_prefix_and_type"
    template = templates[template_key].strip()
    pagination = source.get("pagination") or {}
    rows = int(pagination.get("rows") or 1000)
    select = pagination.get("select_fields") or []
    base = source["base_url"].rstrip("/")

    def build(cursor: str) -> str:
        path = template.format(doi_prefix=scope.prefix, issn=scope.issn, record_type=scope.record_type, rows=rows,
                               cursor=quote(cursor or "*", safe=""), mailto=quote(run_config.mailto, safe="@"),
                               window_filter=window.crossref_filter if window else "")
        return _finish_url(base, path, select)
    return build


def probe_url(run_config: RunConfig, sources_config: Mapping[str, Any], scope: CrossrefScope) -> str:
    """``rows=0`` request that returns only ``total-results`` for the unwindowed scope."""
    source = sources_config["sources"][SOURCE]
    template = source["query_templates"]["works_total_by_prefix_and_type"].strip()
    path = template.format(doi_prefix=scope.prefix, record_type=scope.record_type,
                           mailto=quote(run_config.mailto, safe="@"))
    return source["base_url"].rstrip("/") + path


def parse_crossref_page(body: bytes) -> ParsedPage:
    payload = json.loads(body.decode("utf-8"))
    if payload.get("status") != "ok":
        return ParsedPage(items_in_page=0, next_cursor=None, cursor_invalid=True)
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("items"), list):
        raise ValueError("Crossref page must contain an items array")
    items = message["items"]
    next_cursor = message.get("next-cursor")
    total = message.get("total-results")
    if type(total) is not int or total < 0:
        total = None
    return ParsedPage(len(items), str(next_cursor) if next_cursor else None, total_results=total)


def initial_cursor(sources_config: Mapping[str, Any]) -> str:
    pagination = sources_config["sources"][SOURCE].get("pagination") or {}
    return str(pagination.get("initial_cursor") or "*")


# --------------------------------------------------------------- flattening
def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return "" if value is None else str(value).strip()


def flatten_item(item: Mapping[str, Any], *, platform_id: str, walk: WalkRecord, page: int,
                 accepted_attempt: int, retrieved_at_utc: str) -> dict[str, Any]:
    relation = item.get("relation") or {}
    targets = relation.get("is-review-of") if isinstance(relation, Mapping) else None
    joined = "; ".join(str(t.get("id", "")) for t in targets if isinstance(t, Mapping)) if targets else ""
    raw_doi = str(item.get("DOI", ""))
    return {
        # ``doi`` is the canonical string form (repeated slashes collapsed);
        # ``doi_original`` keeps the deposited string, ``doi_flag`` names the defect.
        "doi": collapse_repeated_slashes(normalise_doi(raw_doi)) if raw_doi else "",
        "doi_original": raw_doi,
        "doi_flag": identifier_flag(raw_doi),
        "type": str(item.get("type", "")),
        "title": _first(item.get("title")),
        "prefix": str(item.get("prefix", "") or ""),
        "member": str(item.get("member", "") or ""),
        "container_title": _first(item.get("container-title")),
        "created": parse_timestamp((item.get("created") or {}).get("date-time")),
        "deposited": parse_timestamp((item.get("deposited") or {}).get("date-time")),
        "indexed": parse_timestamp((item.get("indexed") or {}).get("date-time")),
        "issued": format_partial_date(parse_crossref_date(item.get("issued"))),
        "posted": format_partial_date(parse_crossref_date(item.get("posted"))),
        "published_online": format_partial_date(parse_crossref_date(item.get("published-online"))),
        "published_print": format_partial_date(parse_crossref_date(item.get("published-print"))),
        "relation_is_review_of": joined,
        "relation_json": json.dumps(relation, sort_keys=True, separators=(",", ":")),
        "retrieved_at_utc": retrieved_at_utc,
        "platform_id": platform_id,
        "walk_id": walk.walk_id,
        "page": page,
        "accepted_attempt": accepted_attempt,
    }


def iter_walk_items(store: RawStore, walk: WalkRecord):
    """Yield ``(item, page_entry)`` for every record of a complete walk."""
    if not walk.is_complete:
        raise ExtractionIncomplete(f"walk {walk.walk_id} of scope {walk.scope} is {walk.state}; "
                                   "incomplete walks are never flattened")
    for page in walk.pages:
        payload = store.read_response_json(page.response_path)
        for item in (payload.get("message") or {}).get("items") or []:
            yield item, page


def flatten_works(store: RawStore, walk: WalkRecord, selectors: list[CrossrefSelector]
                  ) -> dict[str, list[dict[str, Any]]]:
    """Split a works walk into per-row interim rows (§4.1)."""
    out: dict[str, list[dict[str, Any]]] = {s.row_id: [] for s in selectors}
    for item, page in iter_walk_items(store, walk):
        for sel in selectors:
            if sel.matches_work(item):
                row = flatten_item(item, platform_id=sel.row_id, walk=walk, page=page.page,
                                                    accepted_attempt=page.accepted_attempt,
                                                    retrieved_at_utc=page.accepted_at_utc)
                if sel.journals:
                    bases = sel.attribution_bases(item)
                    row.update(attribution_basis=";".join(bases), included="" if bases else "false",
                               exclusion_reason="" if bases else "no_journal_attribution")
                elif sel.is_companion_item(item):
                    # Review reports / author responses deposited as journal-article
                    # (JMIRx Med, D-050): kept in the interim, never counted as works.
                    row.update(included="false", exclusion_reason="companion_item")
                out[sel.row_id].append(row)
    return out


def flatten_reviews(store: RawStore, walk: WalkRecord, selectors: list[CrossrefSelector], prefix: str,
                    inverse_targets=None
                    ) -> dict[str, list[dict[str, Any]]]:
    """Split a peer-review walk into per-row interim rows (§4.2).

    Records that no row claims are kept under ``unattributed__<prefix>`` so
    that nothing silently disappears between the raw store and the interim
    layer.
    """
    unattributed = f"unattributed__{prefix}"
    out: dict[str, list[dict[str, Any]]] = {s.row_id: [] for s in selectors}
    out[unattributed] = []
    for item, page in iter_walk_items(store, walk):
        if item.get("type") != REVIEW_RECORD_TYPE and not any(s.is_evaluation_record(item) for s in selectors):
            continue
        targets = review_targets(item)
        inverse = (inverse_targets or {}).get(normalise_doi(item.get("DOI", "")), [])
        if inverse:
            targets = [t for t in targets if t.flag != "missing"]
            known = {t.doi for t in targets if t.doi and not t.flag}
            targets.extend(t for t in inverse if t.doi not in known)
        claimants = [s for s in selectors if s.claims_review(item, targets)]
        keys = [s.row_id for s in claimants] or [unattributed]
        for key in keys:
            base = flatten_item(item, platform_id=key, walk=walk, page=page.page,
                                accepted_attempt=page.accepted_attempt, retrieved_at_utc=page.accepted_at_utc)
            for target in targets:
                out[key].append({**base, "target_id_raw": target.raw, "target_id_type": target.id_type,
                                 "target_flag": target.flag, "target_relation_type": target.relation_type,
                                 "asserted_by": target.asserted_by, "target_doi_flag": target.doi_flag})
    return out


# ------------------------------------------------------------------- driver
def run_crossref(run_config: RunConfig, sources_config: Mapping[str, Any], platforms: list[Mapping[str, Any]],
                 logger, *, kinds: str, raw_root=None, manifest_root: Path | None = None, interim_root=None,
                 transport=None, sleeper=None, force_new_walk: bool = False) -> list[ScopeOutcome]:
    """Walk every scope of ``kinds`` (``works`` or ``reviews``) and flatten complete ones.

    Raises :class:`ExtractionIncomplete` at the end when any scope is not complete,
    after every scope has been attempted and every complete scope flattened.
    """
    selectors = crossref_selectors(platforms)
    scopes = crossref_scopes(selectors, kinds)
    store = RawStore(raw_root)
    manifest_root = Path(manifest_root) if manifest_root else DEFAULT_MANIFEST_ROOT
    interim = resolve_interim_root(interim_root)
    client = build_client(run_config, sources_config, transport=transport, sleeper=sleeper, logger=logger)
    outcomes: list[ScopeOutcome] = []
    accumulated: dict[str, list[dict[str, Any]]] = {}
    blocked: set[str] = set()
    for scope in scopes:
        pagination = sources_config["sources"][SOURCE]["pagination"]
        windowed = windowed_scope_config(pagination, scope.scope_id)
        extra: dict[str, Any] = {}
        if windowed is not None:
            windows = scope_windows(run_config, windowed)
            walker = WindowedWalker(client=client, store=store, manifest_root=manifest_root,
                                    run_id=run_config.run_id, source=SOURCE, scope=scope.scope_id,
                                    windows=windows, granularity=str(windowed["granularity"]), logger=logger)
            walk = walker.run(build_window_url=lambda w: url_builder(run_config, sources_config, scope, w),
                              probe_url=probe_url(run_config, sources_config, scope),
                              parse_page=parse_crossref_page, initial_cursor=initial_cursor(sources_config),
                              force_new_walk=force_new_walk)
            extra["window_set"] = {"date_field": str(windowed["date_field"]),
                                   "granularity": str(windowed["granularity"]),
                                   "first_window_start": windows[1].start.isoformat(),
                                   "reason": str(windowed["reason"]),
                                   "windows": [w.as_record() for w in windows]}
            for window in windows:
                sub_scope = window_scope_id(scope.scope_id, window)
                update_run_manifest_scope(run_manifest_path(manifest_root, run_config.run_id),
                                          run_id=run_config.run_id,
                                          cutoff=run_config.analysis_cutoff_date.isoformat(),
                                          policy=run_config.selected_walk_policy, source=SOURCE, scope=sub_scope,
                                          walks=list_walks(manifest_root, run_config.run_id, SOURCE, sub_scope),
                                          extra={"window_of": scope.scope_id, "window": window.as_record()})
        else:
            tolerance, tolerance_reason = scope_tolerance(pagination, scope.scope_id)
            walker = CursorWalker(client=client, store=store, manifest_root=manifest_root,
                                  run_id=run_config.run_id, source=SOURCE, scope=scope.scope_id, logger=logger,
                                  total_tolerance=tolerance, tolerance_reason=tolerance_reason)
            walk = walker.run(build_url=url_builder(run_config, sources_config, scope),
                              parse_page=parse_crossref_page, initial_cursor=initial_cursor(sources_config),
                              force_new_walk=force_new_walk)
        walks = list_walks(manifest_root, run_config.run_id, SOURCE, scope.scope_id)
        selected, _ = select_walk(walks, run_config.selected_walk_policy)
        if selected is not None:
            walk = selected
        update_run_manifest_scope(run_manifest_path(manifest_root, run_config.run_id), run_id=run_config.run_id,
                                  cutoff=run_config.analysis_cutoff_date.isoformat(),
                                  policy=run_config.selected_walk_policy, source=SOURCE,
                                  scope=scope.scope_id, walks=walks, extra=extra)
        outcome = ScopeOutcome(scope=scope, walk=walk)
        if scope.record_type == REVIEW_RECORD_TYPE:
            dependents = [s for s in selectors if scope.prefix in s.review_prefixes()
                          and REVIEW_RECORD_TYPE in s.record_types]
        elif kinds == "reviews":
            # a work-type walk feeding the review stage (evaluation_record_types)
            dependents = [s for s in selectors if scope.prefix in s.prefixes
                          and scope.record_type in s.evaluation_record_types]
        else:
            dependents = [s for s in selectors if scope.key in s.work_keys()
                          and scope.record_type in s.record_types]
        if not walk.is_complete:
            outcome.blocked_rows = [s.row_id for s in dependents]
            blocked.update(outcome.blocked_rows)
            if logger is not None:
                logger.event("scope_blocked", source=SOURCE, scope=scope.scope_id, walk_state=walk.state,
                             blocked_rows=outcome.blocked_rows)
            outcomes.append(outcome)
            continue
        if kinds == "reviews":
            inverse = inverse_review_targets(run_config, dependents, store, manifest_root)
            tables = flatten_reviews(store, walk, dependents, scope.prefix, inverse)
        else:
            tables = flatten_works(store, walk, dependents)
        for key, rows in tables.items():
            accumulated.setdefault(key, []).extend(rows)
            outcome.rows_written[key] = outcome.rows_written.get(key, 0) + len(rows)
        outcomes.append(outcome)
    # One interim file per row, written only when none of the row's scopes is blocked.
    if kinds == "reviews":
        name, columns = "crossref_peer_reviews", CROSSREF_REVIEW_COLUMNS
    else:
        name, columns = "crossref_works", CROSSREF_WORK_COLUMNS
    for key in sorted(accumulated):
        if key in blocked:
            if logger is not None:
                logger.event("interim_withheld", source=SOURCE, row_id=key,
                             reason="at least one scope of this row is not complete")
            continue
        write_csv(interim / f"{name}__{key}.csv", columns, accumulated[key])
    if kinds == "reviews":
        refresh_journal_attribution(run_config, selectors, store, manifest_root, interim)
    incomplete = [o for o in outcomes if not o.complete]
    if incomplete:
        detail = "; ".join(f"{o.scope.scope_id}: {o.walk.state} (blocks {', '.join(o.blocked_rows) or 'no row'})"
                           for o in incomplete)
        raise ExtractionIncomplete(f"{len(incomplete)} Crossref scope(s) not complete — {detail}")
    return outcomes


def inverse_review_targets(run_config, selectors, store, manifest_root):
    """Use has-review only from selected complete work walks of opted-in rows.

    No network calls, no review/article stem matching and no invented review
    record: an inverse target is used only when its review DOI is retrieved.
    """
    from .selectors import ReviewTarget

    out = {}
    for sel in selectors:
        if not sel.work_correspondences:
            continue
        selected = []
        for scope in crossref_scopes([sel], "works"):
            walk, _ = select_walk(list_walks(manifest_root, run_config.run_id, SOURCE, scope.scope_id),
                                  run_config.selected_walk_policy)
            if walk is None:
                break
            selected.append(walk)
        else:
            for walk in selected:
                for item, _ in iter_walk_items(store, walk):
                    if not sel.matches_work(item):
                        continue
                    work = normalise_doi(item["DOI"])
                    for relation in (item.get("relation") or {}).get("has-review") or []:
                        if not isinstance(relation, Mapping) or relation.get("id-type") != "doi":
                            continue
                        try:
                            review = normalise_doi(relation.get("id", ""))
                        except ValueError:
                            continue
                        if review == work:
                            continue
                        target = ReviewTarget(work, "doi", work, "", "has-review")
                        if target not in out.setdefault(review, []):
                            out[review].append(target)
    return out


def refresh_journal_attribution(run_config, selectors, store, manifest_root, interim):
    """Rebuild journal rows from selected complete walks, joining review evidence.

    Work-stage fields are preliminary until the peer-review stage completes.
    This function performs no requests and never modifies the register.
    """
    for sel in selectors:
        if not sel.journals:
            continue
        required = crossref_scopes([sel])
        selected = []
        for scope in required:
            walk, _ = select_walk(list_walks(manifest_root, run_config.run_id, SOURCE, scope.scope_id),
                                  run_config.selected_walk_policy)
            if walk is None:
                break
            selected.append((scope, walk))
        if len(selected) != len(required):
            continue
        reviewed = set()
        review_walks = []
        for scope in crossref_scopes(selectors, "reviews"):
            walk, _ = select_walk(list_walks(manifest_root, run_config.run_id, SOURCE, scope.scope_id),
                                  run_config.selected_walk_policy)
            if walk is None:
                break
            review_walks.append((scope, walk))
        if len(review_walks) != len(crossref_scopes(selectors, "reviews")):
            continue
        for scope, walk in review_walks:
            for item, _ in iter_walk_items(store, walk):
                if item.get("type") == REVIEW_RECORD_TYPE:
                    reviewed.update(t.doi for t in review_targets(item) if not t.flag and t.doi)
        rows = []
        observed = set()
        yearly = {}
        for scope, walk in selected:
            if scope.record_type == REVIEW_RECORD_TYPE:
                continue
            for item, page in iter_walk_items(store, walk):
                if not sel.matches_work(item):
                    continue
                row = flatten_item(item, platform_id=sel.row_id, walk=walk, page=page.page,
                                   accepted_attempt=page.accepted_attempt,
                                   retrieved_at_utc=page.accepted_at_utc)
                bases = sel.attribution_bases(item, reviewed)
                row.update(attribution_basis=";".join(bases), included="" if bases else "false",
                           exclusion_reason="" if bases else "no_journal_attribution")
                rows.append(row)
                if sel.is_egusphere(row["doi"]):
                    observed.update(bases)
                    year = (row["posted"] or row["issued"] or "")[:4] or "missing_event_date"
                    bucket = yearly.setdefault(year, {"unattributed": 0,
                                                       "coverage": "partial_known_scope"})
                    bucket["unattributed"] += int(not bases)
        write_csv(interim / f"crossref_works__{sel.row_id}.csv", CROSSREF_WORK_COLUMNS, rows)
        path = run_manifest_path(manifest_root, run_config.run_id)
        payload = load_run_manifest(path)
        payload.setdefault("attribution", {})[sel.row_id] = {
            "signals_observed": sorted(observed),
            "effective_register_status": "quantified" if observed else "register_only",
            "fallback_reason": "" if observed else "no_attribution_signal_in_completed_run",
            "yearly_scope": yearly,
            "selected_walks": {s.scope_id: w.walk_id for s, w in selected},
            "review_evidence_walks": {s.scope_id: w.walk_id for s, w in review_walks},
        }
        write_run_manifest(path, payload)
