"""Stage 4 — build the record-level layer ``data/processed/records_<row_id>.csv``.

Input: the per-row interim files written by the extraction stages
(``crossref_works__<row_id>.csv``, ``crossref_peer_reviews__<row_id>.csv``,
``sciety_evaluations__<group_slug>.csv``) and the run manifest.

Output: one record-level file per register row with at least one complete
primary scope, following docs/data_dictionary.md §5.1.  Each line is one of

* ``work_record``          — a Crossref work (posted-content / journal-article);
* ``evaluation_record``    — one evaluation (Crossref peer-review DOI or Sciety
                             DocMap evaluation output);
* ``evaluation_relation``  — one (evaluation, reviewed work) pair.  Every
                             relation line must have its parent evaluation
                             record in the same file (checked, hard failure).

Rules implemented here (and nowhere else):

* identifiers follow the identifier model — ``doi:`` / ``url:`` /
  ``id:<source>:<id>``; the DOI suffix matched by the row's
  ``doi_version_pattern`` is stripped into ``canonical_work_id`` while
  ``work_id`` keeps the DOI as asserted;
* evaluation identity follows the evaluation-identity rule — ``source_evaluation_id``,
  ``evaluation_doi``, ``canonical_evaluation_id`` and the four-valued
  ``evaluation_identity_status``; the Sciety evaluation *URL* is kept in
  ``evaluation_url`` and is never a counting key;
* flagged review targets (placeholder / malformed / self-reference) are kept
  as relation lines with ``record_flag`` and an ``id:`` identifier, so that
  they never join to a work but are not silently dropped;
* Copernicus records keep ``attribution_basis`` and the
  ``no_journal_attribution`` exclusion reason set by the extraction stage;
* no date is imputed: ``event_date_raw`` is the source date at its own precision
  (``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``) or empty.

Rows whose primary scopes are not complete get no records file (an existing
file from an earlier run is removed) and are listed in the stage summary so
that the analysis stage can blank their cells (§9.4, §9.7).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from ..common.config import RunConfig
from ..common.correspondence import canonical_work_doi
from ..common.dates import DateError, parse_partial_date
from ..common.eligibility import canonical_evaluation_id, evaluation_identity_status, unresolved_relations
from ..common.identifiers import IdentifierError, bare_doi, canonical_doi, canonicalise_url, normalise_doi
from ..common.interim import read_csv, resolve_interim_root, write_csv
from ..common.manifest import DEFAULT_MANIFEST_ROOT
from ..common.run_state import RowState, load_row_states
from ..extract.selectors import sciety_scopes

DEFAULT_PROCESSED_ROOT = Path("data/processed")

RECORD_COLUMNS = [
    "row_id", "row_entity_type", "source", "source_record_id", "source_container_id", "source_record_type",
    "review_record_id", "relation_type", "reviewed_work_id", "reviewed_canonical_work_id", "reviewed_work_doi",
    "work_id", "canonical_work_id", "work_doi", "correspondence_basis",
    "source_evaluation_id", "evaluation_doi", "evaluation_url", "canonical_evaluation_id",
    "evaluation_identity_status",
    "event_kind", "event_date_raw", "event_date_precision", "event_interval_start", "event_interval_end",
    "created", "deposited", "indexed", "issued", "posted",
    "title", "container_title", "relation_json", "record_flag", "attribution_basis", "exclusion_reason",
    "retrieved_at_utc", "walk_id", "page",
]
WORK_TYPES = ("posted-content", "journal-article")
WITHDRAWN_RE = re.compile(r"^\s*WITHDRAWN\s*$", re.IGNORECASE)
RECORD_FLAGS = ("", "withdrawn", "placeholder_target", "malformed_target", "self_reference_target",
                "later_version", "missing_target")


class NormalisationError(RuntimeError):
    """Raised when the record-level layer would violate a hard rule."""


# ------------------------------------------------------------------ helpers
def records_path(processed_root: Path, row_id: str) -> Path:
    return Path(processed_root) / f"records_{row_id}.csv"


EMPTY_DATE = {"event_date_raw": "", "event_date_precision": "", "event_interval_start": "", "event_interval_end": ""}


def _parse(value: str) -> dict[str, str]:
    """Date columns for one asserted value; all empty when absent or unparseable — never imputes."""
    try:
        interval = parse_partial_date(value)
    except DateError:
        return dict(EMPTY_DATE)
    if interval is None:
        return dict(EMPTY_DATE)
    return {"event_date_raw": str(value).strip(), "event_date_precision": interval.precision,
            "event_interval_start": interval.start.isoformat(), "event_interval_end": interval.end.isoformat()}


def _date_field_chain(spec: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse ``counting_event_date_field`` ("posted -> issued (note)") into field names."""
    if not spec:
        return default
    chain: list[str] = []
    for token in re.split(r"->|,|/", str(spec)):
        name = re.sub(r"\(.*?\)", "", token).strip().lower().replace(" ", "_")
        if name in ("posted", "issued", "created", "deposited", "indexed", "published_online",
                    "published_print", "evaluation_date"):
            chain.append(name)
    return tuple(chain) or default


def _event_date(interim: Mapping[str, str], chain: tuple[str, ...]) -> dict[str, str]:
    """First asserted date along the configured field chain, at its own precision."""
    for name in chain:
        parsed = _parse(interim.get(name, ""))
        if parsed["event_date_raw"]:
            return parsed
    return dict(EMPTY_DATE)


def _doi_id(doi: str) -> str:
    return f"doi:{doi}" if doi else ""


def _blank_record(row_id: str, entity: str, source: str) -> dict[str, str]:
    rec = {c: "" for c in RECORD_COLUMNS}
    rec.update(row_id=row_id, row_entity_type=entity, source=source)
    return rec


# -------------------------------------------------------------- Crossref works
def work_records(row: Mapping[str, Any], interim_rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    row_id = str(row["row_id"])
    pattern = row.get("doi_version_pattern") or None
    chain = _date_field_chain(row.get("counting_event_date_field"), ("posted", "issued"))
    out: list[dict[str, str]] = []
    for r in interim_rows:
        if r.get("type") not in WORK_TYPES:
            continue
        doi = normalise_doi(r["doi"])
        canonical, basis = canonical_work_doi(row, doi)
        rec = _blank_record(row_id, "work_record", "crossref")
        # The event kind follows the row's counting event, not the Crossref
        # type: an F1000-style version-1 article and a Copernicus discussion
        # paper are postings even when deposited as journal-article.
        kind = "final_article" if row.get("counting_event") == "final_article" else "posting"
        rec.update(_event_date(r, chain))
        rec.update(
            source_record_id=doi, source_record_type=r.get("type", ""),
            work_id=_doi_id(doi), canonical_work_id=_doi_id(canonical), work_doi=canonical,
            correspondence_basis=basis, relation_json=r.get("relation_json", ""),
            event_kind=kind,
            created=r.get("created", ""), deposited=r.get("deposited", ""), indexed=r.get("indexed", ""),
            issued=r.get("issued", ""), posted=r.get("posted", ""),
            title=r.get("title", ""), container_title=r.get("container_title", ""),
            attribution_basis=r.get("attribution_basis", ""),
            exclusion_reason=r.get("exclusion_reason", "") if str(r.get("included", "")).lower() == "false" else "",
            retrieved_at_utc=r.get("retrieved_at_utc", ""), walk_id=r.get("walk_id", ""), page=r.get("page", ""),
        )
        if WITHDRAWN_RE.match(r.get("title", "") or ""):
            rec["record_flag"] = "withdrawn"
        out.append(rec)
    # later_version flag: informational — a work with several version records
    # keeps every record; the earliest-dated one carries the counting event.
    by_work: dict[str, list[dict[str, str]]] = {}
    for rec in out:
        by_work.setdefault(rec["canonical_work_id"], []).append(rec)
    for recs in by_work.values():
        dated = [x for x in recs if x["event_interval_start"]]
        if len(recs) > 1 and dated:
            earliest = min(x["event_interval_start"] for x in dated)
            for x in recs:
                if x["record_flag"] == "" and x["event_interval_start"] and x["event_interval_start"] > earliest:
                    x["record_flag"] = "later_version"
    return out


# -------------------------------------------------------- Crossref peer reviews
def _target_identifier(r: Mapping[str, str], pattern: str | None) -> tuple[str, str, str]:
    """(reviewed_work_id, reviewed_canonical_work_id, record_flag) for one relation line."""
    flag = r.get("target_flag", "")
    raw = r.get("target_id_raw", "")
    id_type = (r.get("target_id_type") or "").lower()
    if flag == "missing":
        return "", "", "missing_target"
    if flag in ("placeholder", "malformed", "self_reference"):
        return f"id:crossref:{raw}", f"id:crossref:{raw}", f"{flag}_target"
    if id_type in ("url", "uri"):
        try:
            wid = f"url:{canonicalise_url(raw)}"
        except IdentifierError:
            return f"id:crossref:{raw}", f"id:crossref:{raw}", "malformed_target"
        return wid, wid, ""
    try:
        doi = normalise_doi(raw)
    except IdentifierError:
        return f"id:crossref:{raw}", f"id:crossref:{raw}", "malformed_target"
    return _doi_id(doi), _doi_id(canonical_doi(doi, pattern)), ""


def review_records(row: Mapping[str, Any], interim_rows: list[Mapping[str, str]],
                   cross_source_dois: set[str]) -> list[dict[str, str]]:
    row_id = str(row["row_id"])
    pattern = row.get("doi_version_pattern") or None
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in interim_rows:
        if r.get("type") != "peer-review":
            continue
        doi = normalise_doi(r["doi"])
        if doi not in seen:
            seen.add(doi)
            rec = _blank_record(row_id, "evaluation_record", "crossref")
            rec.update(_event_date(r, ("issued", "created")))
            rec.update(
                source_record_id=doi, source_record_type="peer-review",
                review_record_id=doi, source_evaluation_id=doi, evaluation_doi=doi,
                canonical_evaluation_id=canonical_evaluation_id(source="crossref", source_evaluation_id=doi,
                                                                evaluation_doi=doi),
                evaluation_identity_status=evaluation_identity_status(
                    source_evaluation_id=doi, evaluation_doi=doi, cross_source_match=doi in cross_source_dois),
                event_kind="evaluation",
                created=r.get("created", ""), deposited=r.get("deposited", ""), indexed=r.get("indexed", ""),
                issued=r.get("issued", ""), posted=r.get("posted", ""),
                title=r.get("title", ""), container_title=r.get("container_title", ""),
                retrieved_at_utc=r.get("retrieved_at_utc", ""), walk_id=r.get("walk_id", ""), page=r.get("page", ""),
            )
            out.append(rec)
        rel = _blank_record(row_id, "evaluation_relation", "crossref")
        wid, cwid, flag = _target_identifier(r, pattern)
        basis = ""
        if not flag and wid.startswith("doi:"):
            canonical, basis = canonical_work_doi(row, bare_doi(wid))
            cwid = _doi_id(canonical)
        rel.update(
            source_record_id=doi, source_record_type="peer-review", review_record_id=doi,
            source_evaluation_id=doi, evaluation_doi=doi,
            canonical_evaluation_id=canonical_evaluation_id(source="crossref", source_evaluation_id=doi,
                                                            evaluation_doi=doi),
            relation_type=r.get("target_relation_type") or "is-review-of",
            reviewed_work_id=wid, reviewed_canonical_work_id=cwid, correspondence_basis=basis,
            reviewed_work_doi=bare_doi(cwid),
            record_flag=flag, retrieved_at_utc=r.get("retrieved_at_utc", ""), walk_id=r.get("walk_id", ""),
            page=r.get("page", ""),
        )
        out.append(rel)
    return out


# ------------------------------------------------------------ Sciety docmaps
def sciety_records(row: Mapping[str, Any], interim_rows: list[Mapping[str, str]],
                   cross_source_dois: set[str]) -> list[dict[str, str]]:
    row_id = str(row["row_id"])
    pattern = row.get("doi_version_pattern") or None
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in interim_rows:
        eval_id = r.get("evaluation_id", "")
        eval_doi = ""
        if r.get("evaluation_doi"):
            try:
                eval_doi = normalise_doi(r["evaluation_doi"])
            except IdentifierError:
                eval_doi = ""
        canonical_eval = canonical_evaluation_id(source="sciety", source_evaluation_id=eval_id, evaluation_doi=eval_doi)
        if eval_id not in seen:
            seen.add(eval_id)
            rec = _blank_record(row_id, "evaluation_record", "sciety")
            rec.update(_parse(r.get("evaluation_date", "")))
            rec.update(
                source_record_id=eval_id, source_container_id=r.get("docmap_id", ""),
                source_record_type=r.get("evaluation_type", "") or "evaluation",
                review_record_id=eval_id, source_evaluation_id=eval_id, evaluation_doi=eval_doi,
                evaluation_url=r.get("evaluation_url", ""), canonical_evaluation_id=canonical_eval,
                evaluation_identity_status=evaluation_identity_status(
                    source_evaluation_id=eval_id, evaluation_doi=eval_doi,
                    cross_source_match=bool(eval_doi) and eval_doi in cross_source_dois),
                event_kind="evaluation",
                retrieved_at_utc=r.get("retrieved_at_utc", ""), walk_id=r.get("walk_id", ""), page=r.get("page", ""),
            )
            out.append(rec)
        rel = _blank_record(row_id, "evaluation_relation", "sciety")
        work_doi_raw = r.get("evaluated_work_doi", "")
        try:
            wdoi = normalise_doi(work_doi_raw) if work_doi_raw else ""
            wid, cwid, flag = (_doi_id(wdoi), _doi_id(canonical_doi(wdoi, pattern)), "") if wdoi \
                else ("", "", "missing_target")
        except IdentifierError:
            wid = cwid = f"id:sciety:{work_doi_raw}"
            flag = "malformed_target"
        rel.update(
            source_record_id=eval_id, source_container_id=r.get("docmap_id", ""),
            source_record_type=r.get("evaluation_type", "") or "evaluation",
            review_record_id=eval_id, source_evaluation_id=eval_id, evaluation_doi=eval_doi,
            evaluation_url=r.get("evaluation_url", ""), canonical_evaluation_id=canonical_eval,
            relation_type="docmap-input", reviewed_work_id=wid, reviewed_canonical_work_id=cwid,
            reviewed_work_doi=bare_doi(cwid), record_flag=flag, retrieved_at_utc=r.get("retrieved_at_utc", ""), walk_id=r.get("walk_id", ""),
            page=r.get("page", ""),
        )
        out.append(rel)
    return out


# ------------------------------------------------------------------- driver
def _sciety_files(row: Mapping[str, Any], interim_root: Path) -> list[Path]:
    return [interim_root / f"sciety_evaluations__{s.group_slug}.csv" for s in sciety_scopes([row])]


def _read_if_exists(path: Path) -> list[Mapping[str, str]]:
    return list(read_csv(path)) if path.exists() else []


def _cross_source_dois(row: Mapping[str, Any], state: RowState, interim_root: Path) -> tuple[set[str], set[str]]:
    """(crossref review DOIs, sciety evaluation DOIs) available for identity confirmation.

    A source contributes only when its scopes are complete — primary or
    cross-check alike; an incomplete cross-check scope confirms nothing.
    """
    crossref: set[str] = set()
    sciety: set[str] = set()
    complete = {k for k, v in {**state.primary_scopes, **state.cross_check_scopes}.items() if v == "complete"}
    if any(k.startswith("crossref/") and k.endswith("__peer-review") for k in complete):
        for r in _read_if_exists(interim_root / f"crossref_peer_reviews__{row['row_id']}.csv"):
            try:
                crossref.add(normalise_doi(r["doi"]))
            except IdentifierError:
                continue
    if any(k.startswith("sciety/") for k in complete):
        for path in _sciety_files(row, interim_root):
            for r in _read_if_exists(path):
                if r.get("evaluation_doi"):
                    try:
                        sciety.add(normalise_doi(r["evaluation_doi"]))
                    except IdentifierError:
                        continue
    return crossref, sciety


def build_row_records(row: Mapping[str, Any], state: RowState, interim_root: Path) -> list[dict[str, str]]:
    """All record lines of one row from its complete scopes (primary sources only)."""
    row_id = str(row["row_id"])
    crossref_dois, sciety_dois = _cross_source_dois(row, state, interim_root)
    records: list[dict[str, str]] = []
    selector = row.get("extraction_selector") or {}
    crossref_role = (selector.get("crossref") or {}).get("role", "primary") if isinstance(selector, Mapping) else "primary"
    sciety_role = (selector.get("sciety") or {}).get("role", "primary") if isinstance(selector, Mapping) else "primary"
    if crossref_role != "cross_check" and any(k.startswith("crossref/") for k in state.primary_scopes):
        works = _read_if_exists(interim_root / f"crossref_works__{row_id}.csv")
        records.extend(work_records(row, works))
        reviews = _read_if_exists(interim_root / f"crossref_peer_reviews__{row_id}.csv")
        records.extend(review_records(row, reviews, sciety_dois))
    if sciety_role != "cross_check" and any(k.startswith("sciety/") for k in state.primary_scopes):
        for path in _sciety_files(row, interim_root):
            records.extend(sciety_records(row, _read_if_exists(path), crossref_dois))
    for rec in records:
        if rec["record_flag"] not in RECORD_FLAGS:
            raise NormalisationError(f"{row_id}: unknown record_flag {rec['record_flag']!r}")
    dangling = unresolved_relations(records)
    if dangling:
        raise NormalisationError(f"{row_id}: {len(dangling)} relation line(s) without a parent evaluation "
                                 f"record, e.g. {dangling[:3]}")
    return records


def run(run_config: RunConfig, sources_config: Mapping[str, Any], platforms: list[Mapping[str, Any]], logger, *,
        interim_root=None, manifest_root: Path | None = None, processed_root: Path | None = None,
        **_ignored) -> dict[str, Any]:
    interim_root = resolve_interim_root(interim_root)
    manifest_root = Path(manifest_root or DEFAULT_MANIFEST_ROOT)
    processed_root = Path(processed_root or DEFAULT_PROCESSED_ROOT)
    processed_root.mkdir(parents=True, exist_ok=True)
    _, states = load_row_states(manifest_root, run_config.run_id, platforms)
    summary: dict[str, Any] = {"run_id": run_config.run_id, "rows": {}}
    for row in platforms:
        row_id = str(row["row_id"])
        state = states[row_id]
        path = records_path(processed_root, row_id)
        if not state.primary_scopes:
            summary["rows"][row_id] = {"status": "no_source", "n_records": 0}
            continue
        if state.extraction_status != "complete":
            if path.exists():
                path.unlink()
            summary["rows"][row_id] = {"status": state.extraction_status, "blocking_scopes": state.blocking_scopes,
                                       "n_records": 0}
            logger.event("normalise_row_blocked", row_id=row_id, extraction_status=state.extraction_status,
                         blocking_scopes=state.blocking_scopes)
            continue
        records = build_row_records(row, state, interim_root)
        n = write_csv(path, RECORD_COLUMNS, records)
        counts = {k: sum(1 for r in records if r["row_entity_type"] == k)
                  for k in ("work_record", "evaluation_record", "evaluation_relation")}
        flagged = sum(1 for r in records if r["record_flag"])
        summary["rows"][row_id] = {"status": "complete", "n_records": n, **counts, "n_flagged": flagged,
                                   "cross_check_complete": state.cross_check_complete}
        logger.event("normalise_row_written", row_id=row_id, path=str(path), n_records=n, **counts)
    (processed_root / "normalisation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
