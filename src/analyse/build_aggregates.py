"""Stage 5 — work-level decisions and every analytical table.

Inputs: ``data/processed/records_<row_id>.csv`` (Stage 4), the run
manifest and the register.  Outputs:

* ``data/processed/works_included.csv``       — one line per (row, canonical work);
* ``data/processed/analysis_manifest.json``   — row states, snapshot window, cutoff;
* ``data/processed/data_quality_log.csv``     — template rows with run counts filled in;
* ``reports/tables/*.csv`` and ``*.md``       — the tables of docs/data_dictionary.md §6.

Rules that live here (and nowhere else):

* the register-row event map: ``counting_event`` and whether a row needs at
  least one qualifying evaluation are read from the register; the posting,
  eligibility-review and counting event groups are kept apart (§9.2, §9.3);
* the cutoff rule and the missingness gates are applied through
  :func:`src.common.eligibility.decide_work` and
  :func:`src.common.aggregates.cell_for` — blanks for register-only rows,
  incomplete scopes, unobservable years and unresolved coverage starts;
  zeros only for complete, observable, empty cells (§8.3, §9.4);
* no table carries an all-row total except the deduplicated
  ``unique_works_all_rows_year.csv``; the Qeios pair must have an empty
  intersection; every other overlap is reported, not removed;
* the cutoff year is labelled ``year_to_date`` whenever the cutoff is not
  31 December; nothing is annualised.

The stage never contacts a network source and never reads raw responses.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..common.aggregates import (AggregateError, Cell, cell_for, check_no_group_total, headline_rows,
                                 is_partial_year, sum_row_series, year_label)
from ..common.config import RunConfig
from ..common.dates import DateInterval, cutoff_status, parse_partial_date
from ..common.eligibility import (EXCLUSION_REASONS, EventRecord, WorkDecision, binding_decision, choose_earliest,
                                  decide_work)
from ..common.interim import read_csv, write_csv
from ..common.manifest import DEFAULT_MANIFEST_ROOT
from ..common.run_state import RowState, load_row_states
from ..normalise.clean_and_normalise import DEFAULT_PROCESSED_ROOT, records_path

DEFAULT_TABLES_ROOT = Path("reports") / "tables"
REQUIRES_EVALUATION_RE = re.compile(r"at least one (?:qualifying )?(?:public )?(?:review|evaluation)", re.IGNORECASE)
# D-060: a first-public-posting row whose eligibility event names the Crossref
# record type ``posted-content`` admits a work only through a posted-content
# record; journal-article records of the same stem are later versions, works
# without a posted-content record are excluded (``no_posting_record``).
REQUIRES_POSTING_RECORD_RE = re.compile(r"\bposted-content\b", re.IGNORECASE)
POSTING_RECORD_TYPE = "posted-content"
FIRST_EVENT_YEAR_POLICY = "first_qualifying_event_year_from_completed_run"
QEIOS_PAIR = ("qeios_hosted_works", "qeios_external_works")

WORKS_COLUMNS = [
    "row_id", "canonical_work_id", "work_doi", "included", "exclusion_reason", "in_eligible_range", "counting_event",
    "posting_event_date_raw", "posting_event_date_precision", "posting_event_interval_start",
    "posting_event_interval_end", "posting_record_id",
    "eligibility_review_event_date_raw", "eligibility_review_event_date_precision",
    "eligibility_review_event_interval_start", "eligibility_review_event_interval_end",
    "eligibility_review_record_id",
    "counting_event_date_raw", "counting_event_date_precision", "counting_event_interval_start",
    "counting_event_interval_end", "counting_record_id",
    "posting_interval_precision", "eligibility_review_interval_precision", "counting_interval_precision",
    "contributing_record_ids", "counting_year", "date_order_ambiguous", "tie_break_source",
    "n_evaluation_records", "n_relations_flagged", "attribution_basis",
    "counting_record_created", "counting_record_deposited", "correspondence_basis",
]
CELL_COLUMNS = ["year", "year_label", "count", "partial_year", "extraction_status", "source_observability_status",
                "observation_status", "coverage", "temporal_coverage_status", "additivity"]
FEATURE_COLUMNS = [
    "row_id", "row_label", "organisation_id", "prc_role", "initiation_class", "classification_confidence",
    "prc_configuration", "configuration_confidence", "binding_publication_decision", "provisional",
    "publish_arrangement", "review_arrangement", "curation_arrangement", "output_types",
    "public_review_reports", "approval_status_public", "summary_assessment", "version_linked_review",
    "public_author_response", "review_has_doi", "reviewer_identity_disclosed", "review_to_object_relation",
    "register_status", "data_status", "data_source",
]
RECOGNITION_SIGNALS = ["public_review_reports", "approval_status_public", "summary_assessment",
                       "version_linked_review", "public_author_response", "review_has_doi"]
DQ_COLUMNS = ["issue_id", "row_id", "issue_type", "description", "evidence", "effect_on_counts", "handling",
              "n_records_affected", "status", "origin", "run_id", "walk_id"]
GROUP_BLOCKING_SOURCE_STATUSES = ("unknown_scope", "pending_run", "selector_no_match",
                                  "source_not_covering")            # D-038 (amended), D-039, D-047, D-058
GROUP_BLOCKING_COVERAGE = ("partial_coverage",)                     # D-038 (amended)
PENDING_RUN = "pending_run"
SELECTOR_NO_MATCH = "selector_no_match"
SOURCE_NOT_COVERING = "source_not_covering"
RECORD_LEVEL_EXCLUSIONS = ("no_journal_attribution", "companion_item")   # set at extraction, carried per record


class AnalysisError(RuntimeError):
    pass


# ------------------------------------------------------------- data classes
@dataclass
class WorkAnalysis:
    row_id: str
    canonical_work_id: str
    work_doi: str
    decision: WorkDecision
    posting: EventRecord | None
    eligibility_review: EventRecord | None
    counting_record: EventRecord | None
    n_relations_flagged: int
    attribution_basis: str
    created: str = ""
    deposited: str = ""
    correspondence_basis: str = ""

    @property
    def included(self) -> bool:
        return self.decision.included

    @property
    def counting_year(self) -> int | None:
        return self.decision.counting_year


@dataclass
class RowAnalysis:
    row: Mapping[str, Any]
    state: RowState
    works: list[WorkAnalysis] = field(default_factory=list)
    eligible_start: int | None = None     # None = unresolved (policy) or not applicable
    eligible_end: int | None = None
    start_unresolved: bool = False
    partial_known_scope_years: set[int] = field(default_factory=set)
    diagnostics: dict[str, int] = field(default_factory=dict)
    effective_register_status: str = ""     # register status after run-derived fallbacks (D-032)
    evaluation_ids_by_year: dict[int, set[str]] = field(default_factory=dict)   # dated evaluations on/before cutoff
    selector_no_match: bool = False         # complete scopes, zero matching records (D-047): never a zero
    source_not_covering: bool = False       # zero records and the source does not carry the group (D-058)

    @property
    def publishable(self) -> bool:
        """A count may be published for this row (register summary, cells)."""
        return (self.complete and self.effective_register_status == "quantified" and not self.start_unresolved
                and not self.selector_no_match and not self.source_not_covering)

    @property
    def row_id(self) -> str:
        return str(self.row["row_id"])

    @property
    def complete(self) -> bool:
        return self.state.extraction_status == "complete" and bool(self.state.primary_scopes)

    def included_works(self) -> list[WorkAnalysis]:
        return [w for w in self.works if w.included]

    def counted_works(self) -> list[WorkAnalysis]:
        """Included works whose counting year lies in the row's eligible range.

        Cells outside the range are ``not_applicable``; the works counted
        there enter no cell and must not enter the register summary or the
        deduplicated group series either (D-060).
        """
        if self.eligible_start is None:
            return self.included_works()
        end = self.eligible_end
        return [w for w in self.included_works()
                if self.eligible_start <= int(w.counting_year) <= (end if end is not None else int(w.counting_year))]  # type: ignore[arg-type]

    def counts_by_year(self) -> dict[int, int]:
        out: dict[int, int] = defaultdict(int)
        for w in self.included_works():
            out[int(w.counting_year)] += 1  # type: ignore[arg-type]
        return dict(out)


# ------------------------------------------------------------------ helpers
def _interval(rec: Mapping[str, str]) -> DateInterval | None:
    if not rec.get("event_interval_start"):
        return None
    return DateInterval(date.fromisoformat(rec["event_interval_start"]), date.fromisoformat(rec["event_interval_end"]),
                        rec.get("event_date_precision", ""), rec.get("event_date_raw", ""))


def _event(rec: Mapping[str, str], kind: str, record_id: str | None = None) -> EventRecord:
    return EventRecord(record_id=record_id or rec["source_record_id"], source=rec["source"], kind=kind,
                       interval=_interval(rec), record_type=rec.get("source_record_type", ""))


def requires_evaluation(row: Mapping[str, Any]) -> bool:
    """A row needs ≥1 qualifying evaluation when its register event list says so."""
    if row.get("counting_event") == "earliest_qualifying_evaluation":
        return False
    events = row.get("eligibility_events") or []
    if isinstance(events, str):
        events = [events]
    return any(REQUIRES_EVALUATION_RE.search(str(e)) for e in events)


def requires_posting_record(row: Mapping[str, Any]) -> bool:
    """A first-public-posting row admits works only through posted-content
    records when its register event list names that record type (D-060)."""
    if row.get("counting_event") != "first_public_posting":
        return False
    events = row.get("eligibility_events") or []
    if isinstance(events, str):
        events = [events]
    return any(REQUIRES_POSTING_RECORD_RE.search(str(e)) for e in events)


def eligible_range(row: Mapping[str, Any], cutoff: date) -> tuple[int | None, int, bool]:
    """``(start, end, unresolved)``; ``start`` is None when the policy defers it to the run."""
    launch = row.get("launch_year")
    start = row.get("coverage_start_year")
    end = row.get("coverage_end_year") or cutoff.year
    selector = row.get("extraction_selector") or {}
    policy = selector.get("coverage_start_policy") if isinstance(selector, Mapping) else None
    if start is None:
        if policy == FIRST_EVENT_YEAR_POLICY:
            return None, int(end), True
        start = launch
    if start is None:
        return None, int(end), True
    return int(max(int(start), int(launch))) if launch else int(start), int(end), False


def effective_register_status(row: Mapping[str, Any], manifest: Mapping[str, Any], complete: bool) -> str:
    """Register status after the run: the Copernicus fallback (D-032) applies only to a complete run.

    The extraction stage records ``attribution[row].effective_register_status``
    as ``register_only`` when none of the three attribution signals appeared
    in the completed walks.  An incomplete run cannot establish absence, so
    the configured status is kept in that case.
    """
    configured = str(row.get("register_status") or "")
    entry = (manifest.get("attribution") or {}).get(str(row["row_id"])) or {}
    effective = entry.get("effective_register_status")
    if complete and effective == "register_only" and configured == "quantified":
        return "register_only"
    return configured


def _parse_ts(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            interval = parse_partial_date(value)
        except Exception:
            return None
        return interval.end if interval else None


# ------------------------------------------------------ per-row work analysis
def analyse_row(row: Mapping[str, Any], state: RowState, records: list[Mapping[str, str]], cutoff: date) -> RowAnalysis:
    analysis = RowAnalysis(row=row, state=state)
    counting_event = str(row.get("counting_event") or "")
    needs_eval = requires_evaluation(row)
    needs_posting_record = requires_posting_record(row)
    works_by_id: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    evaluations: dict[str, Mapping[str, str]] = {}
    relations_by_target: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    flagged_by_target: dict[str, int] = defaultdict(int)
    n_flagged_total = 0
    for rec in records:
        kind = rec["row_entity_type"]
        if kind == "work_record":
            works_by_id[rec["canonical_work_id"]].append(rec)
        elif kind == "evaluation_record":
            evaluations[(rec["source"], rec["review_record_id"])] = rec  # type: ignore[index]
        elif kind == "evaluation_relation":
            if rec.get("record_flag"):
                n_flagged_total += 1
                if rec.get("reviewed_canonical_work_id"):
                    flagged_by_target[rec["reviewed_canonical_work_id"]] += 1
            else:
                relations_by_target[rec["reviewed_canonical_work_id"]].append(rec)
    universe = set(works_by_id)
    if counting_event == "earliest_qualifying_evaluation":
        universe |= set(relations_by_target)
    unlisted_targets = set(relations_by_target) - universe
    analysis.diagnostics.update(
        n_work_records=sum(len(v) for v in works_by_id.values()),
        n_evaluation_records=len(evaluations),
        n_relations=sum(len(v) for v in relations_by_target.values()) + n_flagged_total,
        n_relations_flagged=n_flagged_total,
        n_relation_targets_not_in_row_works=len(unlisted_targets),
        n_evaluations_undated=sum(1 for e in evaluations.values() if not e.get("event_interval_start")),
    )
    for cwid in sorted(universe):
        work_recs = works_by_id.get(cwid, [])
        active = [r for r in work_recs if r.get("record_flag") != "withdrawn"]
        postings = [_event(r, "posting") for r in active if r["event_kind"] == "posting"]
        if needs_posting_record:
            postings = [e for e in postings if e.record_type == POSTING_RECORD_TYPE]
        finals = [_event(r, "final_article") for r in active if r["event_kind"] == "final_article"]
        eval_events: list[EventRecord] = []
        for rel in relations_by_target.get(cwid, []):
            parent = evaluations.get((rel["source"], rel["review_record_id"]))  # type: ignore[arg-type]
            if parent is None:
                raise AnalysisError(f"{row['row_id']}: relation without parent for {rel['review_record_id']}")
            eval_events.append(_event(parent, "evaluation", record_id=parent["canonical_evaluation_id"] or
                                      parent["review_record_id"]))
        bases = sorted({b for r in work_recs for b in (r.get("attribution_basis") or "").split(";") if b})
        title = "WITHDRAWN" if work_recs and not active else ""
        record_reasons = {r.get("exclusion_reason") or "" for r in work_recs}
        if work_recs and len(record_reasons) == 1 and record_reasons <= set(RECORD_LEVEL_EXCLUSIONS):
            # every record of the work carries the same extraction-stage exclusion
            decision = WorkDecision(included=False, exclusion_reason=next(iter(record_reasons)),
                                    n_evaluation_records=len({e.record_id for e in eval_events}))
        elif needs_posting_record and active and not postings:
            # D-060: only journal-article records for this stem (pre-model
            # article, or a version of record whose posting was never deposited)
            decision = WorkDecision(included=False, exclusion_reason="no_posting_record",
                                    n_evaluation_records=len({e.record_id for e in eval_events}))
        else:
            decision = decide_work(counting_event=counting_event, postings=postings, evaluations=eval_events,
                                   finals=finals, cutoff=cutoff, requires_evaluation=needs_eval, title=title)
        posting, _, _ = choose_earliest(postings) if postings else (None, False, "")
        qualifying = [e for e in eval_events if cutoff_status(e.interval, cutoff) == "included"]
        review, _, _ = choose_earliest(qualifying) if qualifying else (None, False, "")
        counting_rec = None
        if decision.counting_record_id:
            pool = postings + eval_events + finals
            counting_rec = next((e for e in pool if e.record_id == decision.counting_record_id), None)
        work_doi = cwid[4:] if cwid.startswith("doi:") else ""
        created = deposited = ""
        if counting_rec is not None:
            src = next((r for r in work_recs if r["source_record_id"] == counting_rec.record_id), None)
            if src is None:
                src = next((e for e in evaluations.values()
                            if (e["canonical_evaluation_id"] or e["review_record_id"]) == counting_rec.record_id), None)
            if src is not None:
                created, deposited = src.get("created", ""), src.get("deposited", "")
        analysis.works.append(WorkAnalysis(
            row_id=str(row["row_id"]), canonical_work_id=cwid, work_doi=work_doi, decision=decision, posting=posting,
            eligibility_review=review, counting_record=counting_rec, n_relations_flagged=flagged_by_target.get(cwid, 0),
            attribution_basis=";".join(bases), created=created, deposited=deposited,
            correspondence_basis=";".join(sorted({r["correspondence_basis"] for r in work_recs
                                                  if r.get("correspondence_basis")}))))
    for reason in EXCLUSION_REASONS:
        analysis.diagnostics[f"excluded_{reason}"] = sum(
            1 for w in analysis.works if not w.included and w.decision.exclusion_reason == reason)
    for (_, _rid), e in evaluations.items():
        interval = _interval(e)
        if interval is not None and cutoff_status(interval, cutoff) == "included":
            analysis.evaluation_ids_by_year.setdefault(interval.year, set()).add(
                e["canonical_evaluation_id"] or e["review_record_id"])
    analysis.diagnostics["n_withdrawn_records"] = sum(
        1 for recs in works_by_id.values() for r in recs if r.get("record_flag") == "withdrawn")
    analysis.diagnostics["n_malformed_doi_records"] = sum(
        1 for rec in records if rec.get("identifier_flag"))
    analysis.diagnostics["n_companion_item_records"] = sum(
        1 for recs in works_by_id.values() for r in recs if r.get("exclusion_reason") == "companion_item")
    analysis.diagnostics["n_included"] = len(analysis.included_works())
    return analysis


def _works_row(w: WorkAnalysis, in_range: bool | None = None) -> dict[str, Any]:
    def group(prefix: str, ev: EventRecord | None) -> dict[str, Any]:
        if ev is None or ev.interval is None:
            return {f"{prefix}_event_date_raw": "", f"{prefix}_event_date_precision": "",
                    f"{prefix}_event_interval_start": "", f"{prefix}_event_interval_end": "",
                    f"{prefix}_interval_precision": ""}
        return {f"{prefix}_event_date_raw": ev.interval.raw, f"{prefix}_event_date_precision": ev.interval.precision,
                f"{prefix}_event_interval_start": ev.interval.start.isoformat(),
                f"{prefix}_event_interval_end": ev.interval.end.isoformat(), f"{prefix}_interval_precision": "source"}
    d = w.decision
    out: dict[str, Any] = {
        "row_id": w.row_id, "canonical_work_id": w.canonical_work_id, "work_doi": w.work_doi,
        "included": "true" if d.included else "false", "exclusion_reason": d.exclusion_reason,
        "in_eligible_range": "" if in_range is None else ("true" if in_range else "false"),
        "counting_event": d.counting_event,
        **group("posting", w.posting), "posting_record_id": w.posting.record_id if w.posting else "",
        **group("eligibility_review", w.eligibility_review),
        "eligibility_review_record_id": w.eligibility_review.record_id if w.eligibility_review else "",
        **group("counting", w.counting_record), "counting_record_id": d.counting_record_id,
        "contributing_record_ids": "; ".join(d.contributing_record_ids),
        "counting_year": d.counting_year if d.counting_year is not None else "",
        "date_order_ambiguous": "true" if d.date_order_ambiguous else "false",
        "tie_break_source": d.tie_break_source, "n_evaluation_records": d.n_evaluation_records,
        "n_relations_flagged": w.n_relations_flagged, "attribution_basis": w.attribution_basis,
        "counting_record_created": w.created, "counting_record_deposited": w.deposited,
        "correspondence_basis": w.correspondence_basis,
    }
    return {c: out.get(c, "") for c in WORKS_COLUMNS}


# ------------------------------------------------------------------ cells
def row_cells(analysis: RowAnalysis, years: Iterable[int], cutoff: date) -> dict[int, Cell]:
    row = analysis.row
    counts = analysis.counts_by_year() if analysis.complete else {}
    cells: dict[int, Cell] = {}
    register_status = analysis.effective_register_status or str(row.get("register_status") or "")
    for year in years:
        in_range = (analysis.eligible_start is not None and analysis.eligible_start <= year <= (analysis.eligible_end or year)) \
            or (analysis.start_unresolved and row.get("launch_year") and int(row["launch_year"]) <= year
                <= (analysis.eligible_end or year))
        observable = not analysis.start_unresolved
        cell = cell_for(
            row_id=analysis.row_id, year=year, cutoff=cutoff, register_status=register_status,
            extraction_status=analysis.state.extraction_status if analysis.state.primary_scopes else "not_applicable",
            source_observable=observable, in_eligible_range=bool(in_range),
            data_status=str(row.get("data_status") or ""),
            n_works=counts.get(year, 0) if analysis.complete else None,
            partial_known_scope=year in analysis.partial_known_scope_years)
        if analysis.start_unresolved and cell.observation_status == "not_observable":
            # Coverage start deferred to the run (D-017): before the first complete run the
            # status is the transient ``pending_run`` (D-039); a complete run without any
            # qualifying event leaves the scope unknown (``unknown_scope``).  Neither is a zero.
            status = "unknown_scope" if analysis.complete else PENDING_RUN
            cell = Cell(cell.row_id, cell.year, None, "not_observable", cell.extraction_status, cell.partial_year,
                        "no_data", status)
        if (analysis.selector_no_match and not analysis.start_unresolved
                and cell.observation_status in ("observed", "observed_zero", "not_observable")):
            # D-047: complete scopes that match no record of the row are a selector
            # defect (wrong owner prefix, pattern or type), not an observation of zero.
            # A row with an unresolved coverage start keeps ``unknown_scope`` (D-039);
            # the data-quality row still names the selector as the cause.
            cell = Cell(cell.row_id, cell.year, None, "not_observable", cell.extraction_status, cell.partial_year,
                        "no_data", SELECTOR_NO_MATCH)
        if (analysis.source_not_covering and not analysis.start_unresolved
                and cell.observation_status in ("observed", "observed_zero", "not_observable")):
            # D-058: the group is absent from the docmaps index retrieved by the same run; the
            # source does not cover it.  Not a selector defect and not a zero.
            cell = Cell(cell.row_id, cell.year, None, "not_observable", cell.extraction_status, cell.partial_year,
                        "no_data", SOURCE_NOT_COVERING)
        cells[year] = cell
    return cells


def _temporal(cell: Cell) -> str:
    if cell.count is None:
        return "not_assessable"
    return "partial" if cell.coverage in ("year_to_date", "partial_coverage", "partial_known_scope") else "complete"


def _cell_fields(cell: Cell, cutoff: date, additivity: str) -> dict[str, Any]:
    return {"year": cell.year, "year_label": year_label(cell.year, cutoff),
            "count": "" if cell.count is None else cell.count,
            "partial_year": "true" if cell.partial_year else "false", "extraction_status": cell.extraction_status,
            "source_observability_status": cell.source_observability_status,
            "observation_status": cell.observation_status, "coverage": cell.coverage,
            "temporal_coverage_status": _temporal(cell), "additivity": additivity}


def _group_members(analyses: list[RowAnalysis], cells: dict[str, dict[int, Cell]], year: int
                   ) -> tuple[list[Cell], list[str]]:
    """In-range member cells of a group for one year and the list of blocking ``row_id:status`` entries.

    D-038 (amended): a group cell is blank only when a member row carries
    ``unknown_scope`` / ``pending_run`` (source observability) or
    ``partial_coverage`` (coverage) for that year, or when the member's
    extraction is not complete (an incomplete scope never contributes to any
    output, §9.4).  ``not_applicable`` and ``observed_zero`` members never
    block the sum.
    """
    members: list[Cell] = []
    blocking: list[str] = []
    for a in analyses:
        cell = cells[a.row_id][year]
        if cell.observation_status in ("not_applicable", "register_only"):
            continue
        members.append(cell)
        if cell.source_observability_status in GROUP_BLOCKING_SOURCE_STATUSES:
            blocking.append(f"{a.row_id}:{cell.source_observability_status}")
        elif cell.coverage in GROUP_BLOCKING_COVERAGE:
            blocking.append(f"{a.row_id}:{cell.coverage}")
        elif cell.count is None:
            blocking.append(f"{a.row_id}:{cell.extraction_status}")
    return members, sorted(blocking)


def _group_cell(value: str, year: int, members: list[Cell], blocking: list[str], count: int | None,
                cutoff: date) -> Cell:
    statuses = {m.extraction_status for m in members}
    ext = "complete" if statuses == {"complete"} else ("failed" if statuses == {"failed"} else "incomplete")
    if blocking or count is None:
        return Cell(value, year, None, "not_observable", ext, is_partial_year(year, cutoff), "no_data",
                    "not_observable")
    covs = {m.coverage for m in members}
    cov = "year_to_date" if is_partial_year(year, cutoff) else ("complete" if covs == {"complete"} else
                                                                 "partial_known_scope" if "partial_known_scope" in covs
                                                                 else "complete")
    src = "partial_known_scope" if "partial_known_scope" in {m.source_observability_status for m in members} \
        else "observable"
    return Cell(value, year, count, "observed" if count else "observed_zero", ext, is_partial_year(year, cutoff),
                cov, src)


def _group_cells(analyses: list[RowAnalysis], cells: dict[str, dict[int, Cell]], years: list[int], cutoff: date,
                 key: str) -> list[dict[str, Any]]:
    """``row_summed`` series per group value (D-038 as amended)."""
    groups: dict[str, list[RowAnalysis]] = defaultdict(list)
    for a in analyses:
        groups[str(a.row[key])].append(a)
    out = []
    for value in sorted(groups):
        for year in years:
            members, blocking = _group_members(groups[value], cells, year)
            if not members:
                continue
            total = None if blocking else sum(int(m.count) for m in members)  # type: ignore[arg-type]
            cell = _group_cell(value, year, members, blocking, total, cutoff)
            out.append({key: value, **_cell_fields(cell, cutoff, "row_summed"), "blocking_rows": "; ".join(blocking)})
    return out


def _dedup_cells(analyses: list[RowAnalysis], cells: dict[str, dict[int, Cell]], years: list[int], cutoff: date,
                 key: str | None) -> list[dict[str, Any]]:
    """``deduplicated`` series: a canonical work counts once per group at its earliest counting year."""
    groups: dict[str, list[RowAnalysis]] = defaultdict(list)
    for a in analyses:
        groups[str(a.row[key]) if key else "all"].append(a)
    out = []
    for value in sorted(groups):
        earliest: dict[str, tuple[int, str, str]] = {}
        for a in groups[value]:
            for w in a.counted_works():
                item = (int(w.counting_year), w.counting_record.interval.start.isoformat() if w.counting_record
                        and w.counting_record.interval else "", a.row_id)
                if w.canonical_work_id not in earliest or item < earliest[w.canonical_work_id]:
                    earliest[w.canonical_work_id] = item
        per_year: dict[int, int] = defaultdict(int)
        per_year_class: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        by_row = {a.row_id: a for a in groups[value]}
        for cwid, (year, _, row_id) in earliest.items():
            per_year[year] += 1
            per_year_class[year][str(by_row[row_id].row["initiation_class"])] += 1
        for year in years:
            members, blocking = _group_members(groups[value], cells, year)
            if not members:
                continue
            blank = bool(blocking)
            count = None if blank else per_year.get(year, 0)
            cell = _group_cell(value, year, members, blocking, count, cutoff)
            line = {**({key: value} if key else {}), **_cell_fields(cell, cutoff, "deduplicated"),
                    "blocking_rows": "; ".join(blocking)}
            if key is None:
                for cls in ("author_initiated", "community_initiated", "mixed"):
                    line[f"n_{cls}_by_earliest_event"] = "" if blank else per_year_class[year].get(cls, 0)
            out.append(line)
    return out


# ----------------------------------------------------------------- tables
def _write_table(tables_root: Path, name: str, columns: list[str], rows: list[Mapping[str, Any]], *, cutoff: date,
                 additivity: str, snapshot: str, note: str = "", footnotes: bool = False) -> None:
    tables_root.mkdir(parents=True, exist_ok=True)
    write_csv(tables_root / f"{name}.csv", columns, rows)
    partial = not (cutoff.month == 12 and cutoff.day == 31)
    lines = [f"# {name}", "",
             f"Analysis cutoff: {cutoff.isoformat()}"
             + (f"; year {cutoff.year} is year_to_date (not annualised)." if partial else "."),
             f"Additivity: `{additivity}`." + (" No all-row total is published in this table." if additivity != "deduplicated"
                                                or "all_rows" not in name else ""),
             f"Snapshot: Crossref/Sciety retrieval finished {snapshot or 'n/a'}.",
             "Empty cells are not zeros: see `observation_status` and `extraction_status` in the CSV.",
             ]
    if note:
        lines.append(note)
    lines += ["", "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
    if footnotes:
        blanks = [r for r in rows if r.get("blocking_rows")]
        lines += ["", "Blank group cells (D-038): the member row and status that block the sum."]
        if not blanks:
            lines.append("None in this table.")
        for r in blanks:
            group = next((str(r[c]) for c in columns if c in ("initiation_class", "prc_configuration")), "all rows")
            lines.append(f"- {group}, {r['year']}: {r['blocking_rows']}")
    (tables_root / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_dq(path: Path) -> list[dict[str, str]]:
    return [dict(r) for r in read_csv(path)] if path.exists() else []


def _index_snapshot_evidence(manifest: Mapping[str, Any], a: RowAnalysis) -> str:
    """Evidence string of a ``source_not_covering`` row: the run's index snapshot and the scope entries."""
    snap = manifest.get("sciety_index_snapshot") or {}
    digest = (snap.get("page_sha256") or [""])[0]
    head = (f"run manifest: sciety_index_snapshot walk {snap.get('walk_id')} "
            f"({snap.get('docmaps_total')} docmaps, retrieved {snap.get('retrieved_at')}"
            + (f", sha256 {digest}" if digest else "") + ")") if snap else "run manifest: sciety_index_snapshot"
    return head + f"; index_coverage of {', '.join(sorted(a.state.primary_scopes))}"


def _coverage_note(a: RowAnalysis, c: Cell, manifest: Mapping[str, Any]) -> str:
    if a.start_unresolved and c.observation_status == "not_observable":
        return "coverage start unresolved; no zero filling"
    if c.source_observability_status == SOURCE_NOT_COVERING:
        retrieved = (manifest.get("sciety_index_snapshot") or {}).get("retrieved_at") or "this run"
        return f"group absent from the Sciety docmaps index retrieved {retrieved}; no zero filling (D-058)"
    if c.coverage == "partial_known_scope":
        return "yearly lower bound: unattributed EGUsphere preprints excluded"
    return ""


def update_data_quality_log(path: Path, analyses: dict[str, RowAnalysis], manifest: Mapping[str, Any]) -> list[dict]:
    """Append run-observed issues to the single log file (D-040).

    Preset rows (``origin = preset``) are never modified.  Rows of the
    current ``run_id`` are replaced; rows of other runs are kept.  Every run
    row carries ``origin = run``, ``run_id`` and the selected ``walk_id``(s) of
    the row's primary scopes.
    """
    run_id = str(manifest.get("run_id") or "")
    existing = _load_dq(path)
    for r in existing:
        r.setdefault("origin", "preset")
        r.setdefault("run_id", "")
        r.setdefault("walk_id", "")
    rows = [r for r in existing if not (r.get("origin") == "run" and r.get("run_id") == run_id)]
    cutoff = a_cutoff(manifest)
    counter = 0

    def observe(a: RowAnalysis, issue_type: str, n: int, description: str, handling: str, effect: str,
                evidence: str = "works_included.csv") -> None:
        nonlocal counter
        if n == 0:
            return
        counter += 1
        walks = "; ".join(f"{k}={v}" for k, v in sorted(a.state.selected_walks.items())
                          if k in a.state.primary_scopes and v)
        rows.append({"issue_id": f"DQ-{run_id}-{counter:03d}", "row_id": a.row_id, "issue_type": issue_type,
                     "description": description, "evidence": evidence, "effect_on_counts": effect,
                     "handling": handling, "n_records_affected": str(n), "status": "observed", "origin": "run",
                     "run_id": run_id, "walk_id": walks})

    for a in analyses.values():
        if not a.complete:
            continue
        d = a.diagnostics
        observe(a, "placeholder_relation", d.get("n_relations_flagged", 0),
                "Review relations with placeholder, malformed, self-referential or missing targets.",
                "Kept as flagged relation lines; never joined to a work.", "none on counts",
                f"records_{a.row_id}.csv (record_flag)")
        observe(a, "withdrawn_record", d.get("n_withdrawn_records", 0),
                "Work records titled WITHDRAWN.", "Record dropped before eligibility.", "lowers the row count",
                f"records_{a.row_id}.csv (record_flag=withdrawn)")
        observe(a, SELECTOR_NO_MATCH, 1 if a.selector_no_match else 0,
                "All primary scopes complete but the row's selector matched no work and no evaluation record "
                "(owner prefix, DOI pattern or record type mismatch).",
                "Every cell of the row is not_observable with source_observability_status=selector_no_match; "
                "register_summary.unique_works_to_cutoff is blank; group sums that include the row are blank. "
                "Correct the selector before the next extraction (tools/check_register_prefixes.py).",
                "no count published for the row", f"run manifest: scopes of {a.row_id}")
        observe(a, SOURCE_NOT_COVERING, 1 if a.source_not_covering else 0,
                "All primary scopes complete with zero docmaps, and the row's Sciety group is absent from the "
                "unfiltered docmaps index retrieved by the same run; the index lists only the groups Sciety has "
                "enabled for docmaps, so the source does not cover the group.",
                "Every cell of the row is not_observable with source_observability_status=source_not_covering; "
                "register_summary.unique_works_to_cutoff is blank; group sums that include the row are blank. "
                "The zero is a property of the source, never an observation of the platform; a count needs an "
                "admissible source named in the register (D-058).",
                "no count published for the row", _index_snapshot_evidence(manifest, a))
        observe(a, "malformed_doi", d.get("n_malformed_doi_records", 0),
                "Records or relation lines whose DOI string was deposited with a repeated slash (10.x//y).",
                "Raw string kept in source_record_id / target_id_raw; canonical identifiers use the single-slash "
                "form (identifier_flag=repeated_slash).", "none on counts; restores records a strict match would lose",
                f"records_{a.row_id}.csv (identifier_flag)")
        observe(a, "companion_record", d.get("n_companion_item_records", 0),
                "Review reports or author responses deposited as journal-article records in the row's container.",
                "Kept in the works interim with included=false and exclusion_reason=companion_item; never counted "
                "as works; not attributed to articles (no is-review-of relation).", "lowers the row count",
                f"records_{a.row_id}.csv (exclusion_reason=companion_item)")
        observe(a, "missing_event_date", d.get("excluded_missing_event_date", 0),
                "Works whose counting event has no asserted date.", "Excluded; never imputed.",
                "lowers the row count")
        observe(a, "ambiguous_cutoff_date", d.get("excluded_ambiguous_cutoff_date", 0),
                "Works whose partial-precision event interval straddles the cutoff.",
                "Excluded; reported in works_included.csv.", "lowers the cutoff-year count")
        observe(a, "partial_source_coverage", d.get("excluded_no_journal_attribution", 0),
                "EGUsphere preprints without any journal-attribution signal.",
                "Retained with included=false and exclusion_reason=no_journal_attribution; "
                "yearly coverage labelled partial_known_scope.", "lower bound for affected years")
        after = sum(1 for w in a.included_works() if (_parse_ts(w.created) or date.min) > cutoff)
        observe(a, "retrospective_deposit", after,
                "Included counting events whose Crossref created date is after the cutoff.",
                "Counted (the event date governs); reported as a deposition diagnostic.", "none on counts")
        if d.get("coverage_start_resolved_from_run"):
            observe(a, "other", 1,
                    f"Coverage start resolved from the run: first observed counting year "
                    f"{d['coverage_start_resolved_from_run']} (model_since to be set in the register).",
                    "Years before the observed start are not_applicable; no zero filling.", "defines the eligible range")
    write_csv(path, DQ_COLUMNS, rows)
    return rows


def a_cutoff(manifest: Mapping[str, Any]) -> date:
    value = manifest.get("analysis_cutoff_date")
    return date.fromisoformat(value) if value else date.max


# ------------------------------------------------------------------- driver
def run(run_config: RunConfig, sources_config: Mapping[str, Any], platforms: list[Mapping[str, Any]], logger, *,
        processed_root: Path | None = None, manifest_root: Path | None = None, tables_root: Path | None = None,
        **_ignored) -> dict[str, Any]:
    cutoff = run_config.analysis_cutoff_date
    processed_root = Path(processed_root or DEFAULT_PROCESSED_ROOT)
    manifest_root = Path(manifest_root or DEFAULT_MANIFEST_ROOT)
    tables_root = Path(tables_root or DEFAULT_TABLES_ROOT)
    manifest, states = load_row_states(manifest_root, run_config.run_id, platforms)
    if manifest.get("analysis_cutoff_date") and manifest["analysis_cutoff_date"] != cutoff.isoformat():
        raise AnalysisError(f"run manifest cutoff {manifest['analysis_cutoff_date']} differs from config "
                            f"{cutoff.isoformat()}; one cutoff per run_id")
    snapshot = str(manifest.get("retrieval_finished_at") or manifest.get("retrieval_started_at") or "")
    attribution = manifest.get("attribution") or {}

    analyses: dict[str, RowAnalysis] = {}
    for row in platforms:
        row_id = str(row["row_id"])
        state = states[row_id]
        path = records_path(processed_root, row_id)
        records = list(read_csv(path)) if (path.exists() and state.extraction_status == "complete") else []
        a = analyse_row(row, state, records, cutoff) if records or state.extraction_status == "complete" \
            else RowAnalysis(row=row, state=state)
        start, end, unresolved = eligible_range(row, cutoff)
        if unresolved and a.complete and a.included_works():
            start, unresolved = min(int(w.counting_year) for w in a.included_works()), False  # type: ignore[arg-type]
            a.diagnostics["coverage_start_resolved_from_run"] = start
        a.eligible_start, a.eligible_end, a.start_unresolved = start, end, unresolved
        a.effective_register_status = effective_register_status(row, manifest, a.complete)
        if (a.complete and a.effective_register_status == "quantified"
                and a.diagnostics.get("n_work_records", 0) == 0 and a.diagnostics.get("n_evaluation_records", 0) == 0):
            # D-047 guard: zero records across all complete scopes is never observed_zero.
            if a.state.source_not_covering:
                # D-058: every primary scope is a Sciety group absent from the run's index snapshot.
                a.source_not_covering = True
                a.diagnostics[SOURCE_NOT_COVERING] = 1
                logger.event(SOURCE_NOT_COVERING, row_id=row_id, scopes=sorted(a.state.primary_scopes))
            else:
                a.selector_no_match = True
                a.diagnostics[SELECTOR_NO_MATCH] = 1
                logger.event(SELECTOR_NO_MATCH, row_id=row_id,
                             scopes=sorted(a.state.primary_scopes))
        if a.effective_register_status == "register_only":
            a.diagnostics["register_only_fallback"] = 1
            logger.event("register_only_fallback", row_id=row_id,
                         reason=(attribution.get(row_id) or {}).get("fallback_reason", ""))
        scope = (attribution.get(row_id) or {}).get("yearly_scope") or {}
        a.partial_known_scope_years = {int(y) for y, v in scope.items()
                                       if isinstance(v, Mapping) and v.get("coverage") == "partial_known_scope"}
        analyses[row_id] = a

    # Qeios disjointness (hard rule) and overlap table
    included_by_work: dict[str, list[WorkAnalysis]] = defaultdict(list)   # disjointness: every included work
    counted_by_work: dict[str, list[WorkAnalysis]] = defaultdict(list)    # overlap table: eligible range (D-060)
    for a in analyses.values():
        for w in a.included_works():
            included_by_work[w.canonical_work_id].append(w)
        for w in a.counted_works():
            counted_by_work[w.canonical_work_id].append(w)
    qeios_overlap = [cw for cw, ws in included_by_work.items() if {w.row_id for w in ws} >= set(QEIOS_PAIR)]
    if qeios_overlap:
        raise AggregateError(f"Qeios rows share {len(qeios_overlap)} included work(s), e.g. {qeios_overlap[:3]}")

    years = list(range(min(int(a.eligible_start or a.row.get("launch_year") or cutoff.year)
                           for a in analyses.values() if a.row.get("register_status") == "quantified"),
                       cutoff.year + 1))
    cells = {a.row_id: row_cells(a, years, cutoff) for a in analyses.values()}
    headline_ids = {str(r["row_id"]) for r in headline_rows(platforms)}
    headline = [a for a in analyses.values() if a.row_id in headline_ids
                and a.effective_register_status != "register_only"]

    processed_root.mkdir(parents=True, exist_ok=True)
    works_rows = []
    for a in analyses.values():
        counted_ids = {id(w) for w in a.counted_works()}
        works_rows.extend(_works_row(w, (id(w) in counted_ids) if w.included else None) for w in a.works)
    write_csv(processed_root / "works_included.csv", WORKS_COLUMNS, works_rows)

    # --- tables
    by_row = [{"row_id": a.row_id, **_cell_fields(c, cutoff, "row_series")}
              for a in analyses.values() for c in cells[a.row_id].values()]
    _write_table(tables_root, "works_by_row_year", ["row_id", *CELL_COLUMNS], by_row, cutoff=cutoff,
                 additivity="row_series", snapshot=snapshot)
    for key, name in (("initiation_class", "works_by_class_year"), ("prc_configuration", "works_by_configuration_year")):
        check_no_group_total(name, "row_summed", [key])
        _write_table(tables_root, name, [key, *CELL_COLUMNS, "blocking_rows"],
                     _group_cells(headline, cells, years, cutoff, key), cutoff=cutoff, additivity="row_summed",
                     snapshot=snapshot, note="Provisional and register-only rows are excluded from this table.",
                     footnotes=True)
    for key, name in (("initiation_class", "unique_works_by_class_year"),
                      ("prc_configuration", "unique_works_by_configuration_year")):
        _write_table(tables_root, name, [key, *CELL_COLUMNS, "blocking_rows"],
                     _dedup_cells(headline, cells, years, cutoff, key), cutoff=cutoff, additivity="deduplicated",
                     snapshot=snapshot, footnotes=True,
                     note="A canonical work counts once per group, in the year of its earliest counting event.")
    all_rows = _dedup_cells(headline, cells, years, cutoff, None)
    _write_table(tables_root, "unique_works_all_rows_year",
                 [*CELL_COLUMNS, "n_author_initiated_by_earliest_event", "n_community_initiated_by_earliest_event",
                  "n_mixed_by_earliest_event", "blocking_rows"], all_rows, cutoff=cutoff, additivity="deduplicated",
                 snapshot=snapshot, footnotes=True,
                 note="The only all-row total; overlapping works are attributed to the class of their earliest event.")

    # register summary
    summary_rows = []
    for a in analyses.values():
        row = a.row
        inc = a.included_works() if a.complete else []
        counted = a.counted_works() if a.complete else []      # D-060: eligible range only
        yrs = sorted({int(w.counting_year) for w in counted})  # type: ignore[arg-type]
        publishable = a.publishable
        summary_rows.append({
            "row_id": a.row_id, "organisation_id": row.get("organisation_id", ""),
            "initiation_class": row.get("initiation_class", ""),
            "classification_confidence": row.get("classification_confidence", ""),
            "prc_configuration": row.get("prc_configuration", ""),
            "configuration_confidence": row.get("configuration_confidence", ""),
            "register_status": row.get("register_status", ""),
            "effective_register_status": a.effective_register_status, "data_status": row.get("data_status", ""),
            "data_source": row.get("data_source", ""), "provisional": "true" if row.get("provisional") else "false",
            "extraction_status": a.state.extraction_status if a.state.primary_scopes else "",
            "eligible_start_year": a.eligible_start if a.eligible_start is not None else "",
            "eligible_end_year": a.eligible_end if a.eligible_end is not None else "",
            "first_year_with_data": yrs[0] if (publishable and yrs) else "",
            "last_year_with_data": yrs[-1] if (publishable and yrs) else "",
            "unique_works_to_cutoff": len({w.canonical_work_id for w in counted}) if publishable else "",
            "n_works_excluded": len(a.works) - len(inc) if publishable else "",
            "n_works_outside_eligible_range": len(inc) - len(counted) if publishable else "",
        })
    _write_table(tables_root, "register_summary", list(summary_rows[0].keys()), summary_rows, cutoff=cutoff,
                 additivity="row_series", snapshot=snapshot,
                 note="`unique_works_to_cutoff` is blank for register-only rows, blocked extraction, an unresolved "
                      "coverage start, a selector that matched no record (selector_no_match) or a source that "
                      "does not cover the group (source_not_covering). `unique_works_to_cutoff`, "
                      "`first_year_with_data` and `last_year_with_data` cover the eligible range only; included "
                      "works counted outside it are reported in `n_works_outside_eligible_range` (D-060).")

    # coverage matrix
    coverage_rows = []
    for a in analyses.values():
        for c in cells[a.row_id].values():
            coverage_rows.append({"row_id": a.row_id, "year": c.year, "year_label": year_label(c.year, cutoff),
                                  "coverage": c.coverage, "partial_year": "true" if c.partial_year else "false",
                                  "extraction_status": c.extraction_status,
                                  "source_observability_status": c.source_observability_status,
                                  "observation_status": c.observation_status,
                                  "note": _coverage_note(a, c, manifest)})
    _write_table(tables_root, "coverage_matrix", list(coverage_rows[0].keys()), coverage_rows, cutoff=cutoff,
                 additivity="row_series", snapshot=snapshot)

    # overlap (reported, never removed)
    overlap_rows = []
    for cw, ws in sorted(counted_by_work.items()):
        if len({w.row_id for w in ws}) < 2:
            continue
        earliest = min(ws, key=lambda w: (w.counting_record.interval.start if w.counting_record and
                                           w.counting_record.interval else date.max, w.row_id))
        overlap_rows.append({"canonical_work_id": cw, "row_ids": "; ".join(sorted({w.row_id for w in ws})),
                             "n_rows": len({w.row_id for w in ws}), "earliest_row_id": earliest.row_id,
                             "earliest_year": earliest.counting_year, "correspondence_basis": "canonical_work_id"})
    _write_table(tables_root, "cross_platform_overlap",
                 ["canonical_work_id", "row_ids", "n_rows", "earliest_row_id", "earliest_year", "correspondence_basis"],
                 overlap_rows, cutoff=cutoff, additivity="row_series", snapshot=snapshot,
                 note="Overlap is reported, not removed; the Qeios pair must be absent here (hard check).")

    # Qeios indicators (§8.10)
    _write_table(tables_root, "qeios_indicators_by_year", ["year", "year_label", "new_hosted_works",
                 "hosted_works_with_review", "review_dois", "external_works_reviewed",
                 "events_registered_after_cutoff_counted", "events_redeposited_after_cutoff_counted",
                 "extraction_status"], qeios_indicators(analyses, years, cutoff), cutoff=cutoff,
                 additivity="row_series", snapshot=snapshot,
                 note="Deposition diagnostics: `created`/`deposited` after the cutoff is reported, never used to "
                      "infer that a record was absent at the cutoff.")

    # evidence features (register fields + the derived binding decision)
    features = []
    for row in platforms:
        decision = binding_decision(str(row.get("prc_configuration") or ""), bool(row.get("provisional")))
        line = {}
        for c in FEATURE_COLUMNS:
            value = row.get(c, "")
            if isinstance(value, bool):
                value = "true" if value else "false"
            line[c] = "; ".join(str(v) for v in value) if isinstance(value, list) else ("" if value is None else value)
        line["provisional"] = "true" if row.get("provisional") else "false"
        line["binding_publication_decision"] = "" if decision is None else ("true" if decision else "false")
        features.append(line)
    _write_table(tables_root, "evidence_features_by_platform", FEATURE_COLUMNS, features, cutoff=cutoff,
                 additivity="row_series", snapshot=snapshot,
                 note="`binding_publication_decision` is derived from `prc_configuration` and is contextual, "
                      "not a recognition signal.")

    dq_rows = update_data_quality_log(processed_root / "data_quality_log.csv", analyses, manifest)

    analysis_manifest = {
        "run_id": run_config.run_id, "analysis_cutoff_date": cutoff.isoformat(), "snapshot_finished_at": snapshot,
        "years": years, "rows": {
            a.row_id: {"extraction_status": a.state.extraction_status if a.state.primary_scopes else "no_source",
                       "effective_register_status": a.effective_register_status,
                       "cross_check_scopes": a.state.cross_check_scopes,
                       "blocking_scopes": a.state.blocking_scopes, "eligible_start": a.eligible_start,
                       "eligible_end": a.eligible_end, "start_unresolved": a.start_unresolved,
                       "selector_no_match": a.selector_no_match,
                       "source_not_covering": a.source_not_covering,
                       "index_coverage": a.state.index_coverage,
                       "partial_known_scope_years": sorted(a.partial_known_scope_years),
                       "diagnostics": a.diagnostics} for a in analyses.values()},
        "n_data_quality_issues_observed": sum(1 for r in dq_rows if r["status"] == "observed"),
    }
    (processed_root / "analysis_manifest.json").write_text(json.dumps(analysis_manifest, indent=2, sort_keys=True) + "\n")
    logger.event("analysis_complete", n_rows=len(analyses), n_works=len(works_rows),
                 blocked_rows=[a.row_id for a in analyses.values() if a.state.primary_scopes and not a.complete])
    return analysis_manifest


def qeios_indicators(analyses: Mapping[str, RowAnalysis], years: list[int], cutoff: date) -> list[dict[str, Any]]:
    hosted, external = analyses.get(QEIOS_PAIR[0]), analyses.get(QEIOS_PAIR[1])
    rows = []
    for year in years:
        line: dict[str, Any] = {"year": year, "year_label": year_label(year, cutoff), "new_hosted_works": "",
                                "hosted_works_with_review": "", "review_dois": "", "external_works_reviewed": "",
                                "events_registered_after_cutoff_counted": "",
                                "events_redeposited_after_cutoff_counted": "", "extraction_status": ""}
        if hosted is None or external is None:
            rows.append(line)
            continue
        statuses = {hosted.state.extraction_status, external.state.extraction_status}
        line["extraction_status"] = "complete" if statuses == {"complete"} else "incomplete"
        start = min(x for x in (hosted.eligible_start, external.eligible_start) if x is not None) \
            if (hosted.eligible_start or external.eligible_start) else None
        if statuses != {"complete"} or start is None or year < start:
            rows.append(line)
            continue
        new_hosted = sum(1 for w in hosted.works if w.posting and w.posting.interval
                         and w.decision.exclusion_reason != "withdrawn"
                         and cutoff_status(w.posting.interval, cutoff) == "included"
                         and w.posting.interval.year == year)
        with_review = sum(1 for w in hosted.included_works() if w.counting_year == year)
        review_dois = set(hosted.evaluation_ids_by_year.get(year, set())) | set(
            external.evaluation_ids_by_year.get(year, set()))
        line.update(new_hosted_works=new_hosted, hosted_works_with_review=with_review, review_dois=len(review_dois),
                    external_works_reviewed=sum(1 for w in external.included_works() if w.counting_year == year),
                    events_registered_after_cutoff_counted=sum(
                        1 for a in (hosted, external) for w in a.included_works()
                        if w.counting_year == year and (_parse_ts(w.created) or date.min) > cutoff),
                    events_redeposited_after_cutoff_counted=sum(
                        1 for a in (hosted, external) for w in a.included_works()
                        if w.counting_year == year and (_parse_ts(w.deposited) or date.min) > cutoff))
        rows.append(line)
    return rows
