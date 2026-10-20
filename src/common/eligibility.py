"""Work-level eligibility and counting-event logic shared by the analysis stage.

Inputs are plain dataclasses so the rules can be exercised offline.  The
functions here decide, for one register row and one canonical work:

* which events exist (posting, qualifying evaluation(s), final article);
* whether the work is included under the cutoff rule;
* the counting event and its counting year;
* the evaluation identity status of every evaluation record.

Nothing here reads files or performs HTTP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .dates import DateInterval, cutoff_status, intervals_overlap

COUNTING_EVENTS = ("first_public_posting", "earliest_qualifying_evaluation", "final_article")
EXCLUSION_REASONS = ("missing_event_date", "ambiguous_cutoff_date", "future_event", "no_qualifying_review",
                     "withdrawn", "later_version", "register_only", "no_journal_attribution")
IDENTITY_STATUSES = ("source_only", "doi_confirmed", "cross_source_confirmed", "unresolved")
WITHDRAWN_TITLE_RE = re.compile(r"^WITHDRAWN$")


@dataclass(frozen=True)
class EventRecord:
    """One dated source record contributing to a work's event map."""
    record_id: str                 # source record id (DOI or sciety:<docmap>:<i>)
    source: str                    # crossref | sciety
    kind: str                      # posting | evaluation | final_article
    interval: DateInterval | None  # None when the source asserted no date
    record_type: str = ""          # Crossref type when applicable
    flag: str = ""                 # withdrawn | later_version | placeholder_target | ...
    created: str = ""              # Crossref registration timestamp; diagnostics only, never an eligibility input


@dataclass
class WorkDecision:
    included: bool
    exclusion_reason: str = ""
    counting_event: str = ""
    counting_interval: DateInterval | None = None
    counting_year: int | None = None
    counting_record_id: str = ""
    date_order_ambiguous: bool = False
    tie_break_source: str = ""
    n_evaluation_records: int = 0
    contributing_record_ids: list[str] = field(default_factory=list)


_PRECISION_RANK = {"day": 0, "month": 1, "year": 2}


def choose_earliest(records: list[EventRecord]) -> tuple[EventRecord | None, bool, str]:
    """Earliest dated record with the deterministic tie-break of §5.2.

    Returns ``(record, date_order_ambiguous, tie_break_source)``.  Records
    without a date are ignored here; the caller decides what their absence
    means.
    """
    dated = [r for r in records if r.interval is not None]
    if not dated:
        return None, False, ""
    earliest_end = min(r.interval.end for r in dated)
    # Candidates: records whose interval could be the earliest (overlapping the leader).
    leader = min(dated, key=lambda r: (r.interval.start, r.interval.end))
    candidates = [r for r in dated if intervals_overlap(r.interval, leader.interval)]
    if len(candidates) == 1:
        return candidates[0], False, ""

    def key(r: EventRecord):
        return (_PRECISION_RANK[r.interval.precision],
                0 if r.source == "crossref" else 1,
                0 if r.record_type == "posted-content" else 1,
                r.record_id)
    chosen = sorted(candidates, key=key)[0]
    ambiguous = any(r.interval != chosen.interval for r in candidates)
    del earliest_end
    return chosen, ambiguous, chosen.source if ambiguous else ""


def decide_work(*, counting_event: str, postings: list[EventRecord], evaluations: list[EventRecord],
                finals: list[EventRecord], cutoff: date, requires_evaluation: bool,
                title: str = "") -> WorkDecision:
    """Apply eligibility and the cutoff rule to one canonical work.

    ``requires_evaluation`` is True for rows whose eligibility needs at least
    one qualifying evaluation dated on or before the cutoff (for example the
    Qeios hosted-works row); the evaluation itself must then be *included*
    under the cutoff rule, not merely present.
    """
    if counting_event not in COUNTING_EVENTS:
        raise ValueError(f"unknown counting_event {counting_event!r}")
    decision = WorkDecision(included=False)
    if title and WITHDRAWN_TITLE_RE.match(title.strip()):
        decision.exclusion_reason = "withdrawn"
        return decision
    unique_eval_ids = {e.record_id for e in evaluations}
    decision.n_evaluation_records = len(unique_eval_ids)

    qualifying = [e for e in evaluations if cutoff_status(e.interval, cutoff) == "included"]
    if requires_evaluation and not qualifying:
        if evaluations and all(e.interval is None for e in evaluations):
            decision.exclusion_reason = "missing_event_date"
        elif evaluations and any(cutoff_status(e.interval, cutoff) == "ambiguous_cutoff_date" for e in evaluations):
            decision.exclusion_reason = "ambiguous_cutoff_date"
        else:
            decision.exclusion_reason = "no_qualifying_review"
        return decision

    if counting_event == "first_public_posting":
        pool = postings
    elif counting_event == "earliest_qualifying_evaluation":
        pool = qualifying if requires_evaluation else evaluations
    else:
        pool = finals
    if not pool:
        decision.exclusion_reason = "no_qualifying_review" if counting_event == "earliest_qualifying_evaluation" \
            else "missing_event_date"
        return decision
    chosen, ambiguous, tie_source = choose_earliest(pool)
    if chosen is None:
        decision.exclusion_reason = "missing_event_date"
        return decision
    status = cutoff_status(chosen.interval, cutoff)
    decision.counting_event = counting_event
    decision.counting_interval = chosen.interval
    decision.counting_record_id = chosen.record_id
    decision.date_order_ambiguous = ambiguous
    decision.tie_break_source = tie_source
    decision.contributing_record_ids = sorted({r.record_id for r in pool})
    if status == "included":
        decision.included = True
        decision.counting_year = chosen.interval.year
    elif status == "future":
        decision.exclusion_reason = "future_event"
    else:
        decision.exclusion_reason = status
    return decision


# ------------------------------------------------------- evaluation identity
def evaluation_identity_status(*, source_evaluation_id: str, evaluation_doi: str,
                               cross_source_match: bool) -> str:
    """Four-valued identity status of one evaluation record.

    * ``cross_source_confirmed`` — the same evaluation was matched in both
      permitted sources (DOI or URL identity);
    * ``doi_confirmed`` — a DOI identifies the evaluation in one source;
    * ``source_only`` — only a source-local identifier exists;
    * ``unresolved`` — no usable identifier at all.
    """
    if cross_source_match:
        return "cross_source_confirmed"
    if evaluation_doi:
        return "doi_confirmed"
    if source_evaluation_id:
        return "source_only"
    return "unresolved"


def canonical_evaluation_id(*, source: str, source_evaluation_id: str, evaluation_doi: str) -> str:
    if evaluation_doi:
        return f"doi:{evaluation_doi}"
    if source_evaluation_id:
        return f"id:{source}:{source_evaluation_id}" if not source_evaluation_id.startswith(f"{source}:") \
            else f"id:{source_evaluation_id}"
    return ""


# ---------------------------------------------------------- parent integrity
def unresolved_relations(records: list[dict]) -> list[tuple[str, str]]:
    """Relation rows whose parent evaluation record is absent (§5.1 rule).

    ``records`` are dictionaries with at least ``row_entity_type``, ``source``
    and ``review_record_id``.  Returns ``(source, review_record_id)`` pairs.
    """
    parents = {(r["source"], r["review_record_id"]) for r in records
               if r.get("row_entity_type") == "evaluation_record"}
    missing = []
    for r in records:
        if r.get("row_entity_type") != "evaluation_relation":
            continue
        key = (r["source"], r["review_record_id"])
        if key not in parents and key not in missing:
            missing.append(key)
    return missing


# ------------------------------------------------------------ binding flag
PRC_CONFIGURATIONS = ("core_publish_first", "approval_threshold", "hybrid_public_discussion",
                      "review_or_curation_service")


def binding_decision(prc_configuration: str, provisional: bool = False) -> bool | None:
    """``binding_publication_decision`` derived from the configuration axis.

    ``hybrid_public_discussion`` -> True; every other configuration -> False;
    ``None`` (empty cell) for a provisional, unresolved configuration.  The
    value is never entered by hand in the register.
    """
    if prc_configuration not in PRC_CONFIGURATIONS:
        raise ValueError(f"unknown prc_configuration {prc_configuration!r}")
    if provisional:
        return None
    return prc_configuration == "hybrid_public_discussion"
