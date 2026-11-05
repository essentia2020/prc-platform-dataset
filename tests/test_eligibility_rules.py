"""Boundary tests 3, 9, 10, 11, 12 and the Qeios rules on synthetic event maps."""

from __future__ import annotations

from datetime import date

import pytest

from src.common.dates import parse_partial_date as d
from src.common.eligibility import (EventRecord, binding_decision, canonical_evaluation_id, choose_earliest,
                                    decide_work, evaluation_identity_status, unresolved_relations)
from src.common.identifiers import canonical_doi, canonicalise_url, work_id_from_url
from src.common.register import load_platforms, platforms_by_row_id

CUTOFF = date(2026, 9, 30)


def posting(rid, when, title="", record_type="posted-content"):
    return EventRecord(rid, "crossref", "posting", d(when), record_type=record_type)


def evaluation(rid, when, source="crossref"):
    return EventRecord(rid, source, "evaluation", d(when))


# ------------------------------------------------------------- Qeios (test 3)
def test_qeios_hosted_work_needs_an_included_review():
    ok = decide_work(counting_event="first_public_posting", postings=[posting("10.32388/aaaa11", "2024-03-11")],
                     evaluations=[evaluation("10.32388/aaaa11.r1", "2024-04-02")], finals=[], cutoff=CUTOFF,
                     requires_evaluation=True)
    assert ok.included and ok.counting_year == 2024 and ok.n_evaluation_records == 1
    late = decide_work(counting_event="first_public_posting", postings=[posting("10.32388/dddd44", "2024")],
                       evaluations=[evaluation("10.32388/dddd44.r1", "2026-11-01")], finals=[], cutoff=CUTOFF,
                       requires_evaluation=True)
    assert not late.included and late.exclusion_reason == "no_qualifying_review"
    none = decide_work(counting_event="first_public_posting", postings=[posting("10.32388/eeee55", "2024-01-01")],
                       evaluations=[], finals=[], cutoff=CUTOFF, requires_evaluation=True)
    assert none.exclusion_reason == "no_qualifying_review"


def test_review_before_cutoff_counts_even_if_registered_after_cutoff():
    # boundary test 1: event-history reconstruction ignores the registration timestamp
    late_registered = EventRecord("10.32388/aaaa11.r1", "crossref", "evaluation", d("2026-09-15"),
                                  created="2026-10-18T09:00:00Z")
    decision = decide_work(counting_event="earliest_qualifying_evaluation", postings=[posting("w", "2026-09-01")],
                           evaluations=[late_registered], finals=[], cutoff=CUTOFF, requires_evaluation=True)
    assert decision.included and decision.counting_year == 2026 and decision.counting_record_id == "10.32388/aaaa11.r1"


def test_year_only_event_in_a_completed_year_counts_for_that_year():
    # boundary test 4
    decision = decide_work(counting_event="first_public_posting", postings=[posting("w", "2024")],
                           evaluations=[evaluation("r", "2024")], finals=[], cutoff=CUTOFF, requires_evaluation=True)
    assert decision.included and decision.counting_year == 2024
    assert decision.counting_interval.precision == "year"


def test_qeios_review_exactly_on_cutoff_qualifies():
    decision = decide_work(counting_event="first_public_posting", postings=[posting("w", "2026-01-01")],
                           evaluations=[evaluation("r", "2026-09-30")], finals=[], cutoff=CUTOFF,
                           requires_evaluation=True)
    assert decision.included and decision.counting_year == 2026


def test_withdrawn_title_excludes_the_work():
    decision = decide_work(counting_event="first_public_posting", postings=[posting("w", "2023-07-01")],
                           evaluations=[evaluation("r", "2023-08-01")], finals=[], cutoff=CUTOFF,
                           requires_evaluation=True, title="WITHDRAWN")
    assert decision.exclusion_reason == "withdrawn"
    kept = decide_work(counting_event="first_public_posting", postings=[posting("w", "2023-07-01")],
                       evaluations=[evaluation("r", "2023-08-01")], finals=[], cutoff=CUTOFF,
                       requires_evaluation=True, title="Withdrawn from consideration: a study")
    assert kept.included   # only the exact title WITHDRAWN triggers the rule


def test_year_only_posting_in_cutoff_year_is_ambiguous_not_counted():
    decision = decide_work(counting_event="first_public_posting", postings=[posting("w", "2026")],
                           evaluations=[], finals=[], cutoff=CUTOFF, requires_evaluation=False)
    assert not decision.included and decision.exclusion_reason == "ambiguous_cutoff_date"
    assert decision.counting_year is None


def test_missing_posting_date_is_never_imputed():
    decision = decide_work(counting_event="first_public_posting",
                           postings=[EventRecord("w", "crossref", "posting", None)], evaluations=[], finals=[],
                           cutoff=CUTOFF, requires_evaluation=False)
    assert decision.exclusion_reason == "missing_event_date"


# --------------------------------------------------- event map (tests 10, 12)
def test_counting_event_follows_the_row_rule():
    postings = [posting("w", "2024-01-10")]
    evaluations = [evaluation("r2", "2024-06-01"), evaluation("r1", "2024-03-01")]
    finals = [EventRecord("f", "crossref", "final_article", d("2025-02-02"), record_type="journal-article")]
    by_posting = decide_work(counting_event="first_public_posting", postings=postings, evaluations=evaluations,
                             finals=finals, cutoff=CUTOFF, requires_evaluation=False)
    by_eval = decide_work(counting_event="earliest_qualifying_evaluation", postings=postings, evaluations=evaluations,
                          finals=finals, cutoff=CUTOFF, requires_evaluation=True)
    by_final = decide_work(counting_event="final_article", postings=postings, evaluations=evaluations,
                           finals=finals, cutoff=CUTOFF, requires_evaluation=False)
    assert (by_posting.counting_record_id, by_posting.counting_year) == ("w", 2024)
    assert (by_eval.counting_record_id, by_eval.counting_year) == ("r1", 2024)
    assert (by_final.counting_record_id, by_final.counting_year) == ("f", 2025)


def test_earliest_evaluation_tie_break_is_deterministic():
    chosen, ambiguous, source = choose_earliest([
        EventRecord("sciety:x:0", "sciety", "evaluation", d("2024-03")),
        EventRecord("10.1/r", "crossref", "evaluation", d("2024-03-15")),
    ])
    assert chosen.record_id == "10.1/r" and ambiguous and source == "crossref"
    chosen, ambiguous, _ = choose_earliest([EventRecord("b", "crossref", "evaluation", d("2024-03-15")),
                                            EventRecord("a", "crossref", "evaluation", d("2024-03-15"))])
    assert chosen.record_id == "a" and not ambiguous


def test_counting_event_declared_for_every_quantified_row():
    for row in load_platforms():
        if row["register_status"] == "quantified":
            assert row["counting_event"] in ("first_public_posting", "earliest_qualifying_evaluation", "final_article")
            assert row["eligibility_events"], row["row_id"]


# ------------------------------------------------ identities (tests 9, 11, 12)
def test_versioned_relation_resolves_to_one_canonical_work():
    rows = platforms_by_row_id(load_platforms())
    pattern = rows["qeios_hosted_works"]["doi_version_pattern"]
    assert pattern, "Qeios rows need a doi_version_pattern"
    assert canonical_doi("10.32388/bbbb22.2", pattern) == canonical_doi("10.32388/bbbb22", pattern)
    assert canonical_doi("10.32388/bbbb22.2", pattern) == "10.32388/bbbb22"
    # asserted and canonical identifiers stay distinct columns and join on the canonical form
    asserted = {"doi:10.32388/bbbb22.2", "doi:10.32388/bbbb22.1"}
    canonical = {f"doi:{canonical_doi(a[4:], pattern)}" for a in asserted}
    assert canonical == {"doi:10.32388/bbbb22"} and asserted != canonical


def test_reviewer_identity_is_four_valued_and_separate_from_tri_state_signals():
    # boundary test 12
    from src.common import register as reg
    rows = load_platforms()
    identity_values = {r["reviewer_identity_disclosed"] for r in rows}
    assert identity_values <= {"always", "optional", "never", "unknown"}
    assert len({"always", "optional", "never", "unknown"}) == 4
    tri_state = {str(r["public_review_reports"]) for r in rows} | {str(r["version_linked_review"]) for r in rows}
    assert tri_state <= {"True", "False", "unknown"}
    csv_text = reg.render_platforms_csv()
    header = csv_text.splitlines()[0].split(",")
    assert "reviewer_identity_disclosed" in header and "public_review_reports" in header


def test_four_valued_evaluation_identity():
    assert evaluation_identity_status(source_evaluation_id="sciety:d:0", evaluation_doi="", cross_source_match=False) == "source_only"
    assert evaluation_identity_status(source_evaluation_id="10.1/r", evaluation_doi="10.1/r", cross_source_match=False) == "doi_confirmed"
    assert evaluation_identity_status(source_evaluation_id="10.1/r", evaluation_doi="10.1/r", cross_source_match=True) == "cross_source_confirmed"
    assert evaluation_identity_status(source_evaluation_id="", evaluation_doi="", cross_source_match=False) == "unresolved"
    assert canonical_evaluation_id(source="sciety", source_evaluation_id="sciety:d:0", evaluation_doi="") == "id:sciety:d:0"
    assert canonical_evaluation_id(source="crossref", source_evaluation_id="10.1/r", evaluation_doi="10.1/r") == "doi:10.1/r"


def test_every_relation_resolves_to_a_parent_record():
    records = [
        {"row_entity_type": "evaluation_record", "source": "crossref", "review_record_id": "10.1/r1"},
        {"row_entity_type": "evaluation_relation", "source": "crossref", "review_record_id": "10.1/r1"},
        {"row_entity_type": "evaluation_relation", "source": "crossref", "review_record_id": "10.1/orphan"},
        {"row_entity_type": "evaluation_relation", "source": "sciety", "review_record_id": "10.1/r1"},
    ]
    assert unresolved_relations(records) == [("crossref", "10.1/orphan"), ("sciety", "10.1/r1")]


def test_binding_decision_is_derived_from_configuration_only():
    assert binding_decision("hybrid_public_discussion") is True
    assert binding_decision("core_publish_first") is False
    assert binding_decision("approval_threshold") is False
    assert binding_decision("review_or_curation_service") is False
    assert binding_decision("core_publish_first", provisional=True) is None
    with pytest.raises(ValueError):
        binding_decision("mixed")
    rows = platforms_by_row_id(load_platforms())
    assert rows["jmirx_med"]["prc_configuration"] == "core_publish_first"
    assert binding_decision(rows["scipost"]["prc_configuration"]) is True
    assert all("binding_publication_decision" not in row for row in rows.values())


def test_url_canonicalisation_lowercases_host_only():
    assert canonicalise_url("HTTPS://Example.ORG/Some/Path?Q=1#Frag") == "HTTPS://example.org/Some/Path?Q=1#Frag"
    assert canonicalise_url("https://example.org/path/") != canonicalise_url("https://example.org/path")
    assert work_id_from_url("https://Example.org/x").startswith("url:https://example.org/")


# ------------------------------------------------------------------- D-073
def test_tie_break_prefers_the_earlier_day_record_over_a_smaller_record_id():
    """Two day-precision records overlap one year-precision record; the earlier day wins, not the smaller id."""
    chosen, ambiguous, source = choose_earliest([
        EventRecord("a-later", "crossref", "evaluation", d("2024-06-20")),
        EventRecord("b-earlier", "crossref", "evaluation", d("2024-02-01")),
        EventRecord("c-year", "crossref", "evaluation", d("2024")),
    ])
    assert chosen.record_id == "b-earlier" and ambiguous and source == "crossref"
    # two records with the same day still fall through to the record id
    chosen, ambiguous, _ = choose_earliest([
        EventRecord("z", "crossref", "evaluation", d("2024-02-01")),
        EventRecord("y", "crossref", "evaluation", d("2024-02-01")),
        EventRecord("c-year", "crossref", "evaluation", d("2024")),
    ])
    assert chosen.record_id == "y" and ambiguous


def test_evaluation_record_without_issued_has_no_interval_and_is_missing_event_date():
    """D-073: ``created`` is never the event date of a Crossref evaluation record."""
    from src.normalise.clean_and_normalise import review_records

    row = {"row_id": "x", "doi_version_pattern": None, "extraction_selector": {"crossref": {}}}
    interim = [{"doi": "10.21956/test.1.r1", "type": "peer-review", "issued": "", "created": "2024-03-01T10:00:00Z",
                "target_doi": "10.12688/test.1.1", "target_relation_type": "is-review-of"}]
    recs = review_records(row, interim, set())
    ev = [r for r in recs if r["row_entity_type"] == "evaluation_record"]
    assert len(ev) == 1
    assert ev[0]["event_date_raw"] == "" and ev[0]["event_interval_start"] == "" and ev[0]["event_interval_end"] == ""
    assert ev[0]["created"] == "2024-03-01T10:00:00Z"      # kept as a diagnostic column
    # downstream: the undated evaluation cannot be a counting event
    decision = decide_work(counting_event="earliest_qualifying_evaluation", postings=[],
                           evaluations=[EventRecord("10.21956/test.1.r1", "crossref", "evaluation", None)], finals=[],
                           cutoff=CUTOFF, requires_evaluation=False)
    assert not decision.included and decision.exclusion_reason == "missing_event_date"
