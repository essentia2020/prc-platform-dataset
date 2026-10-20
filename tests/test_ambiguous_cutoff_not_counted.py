"""§8.1/§8.3: partial-precision intervals straddling the cutoff are excluded, not rounded."""

from datetime import date

from src.common.dates import DateInterval, cutoff_status
from src.common.eligibility import EventRecord, decide_work


def test_year_precision_event_in_cutoff_year_is_ambiguous():
    interval = DateInterval(date(2026, 1, 1), date(2026, 12, 31), "year", "2026")
    assert cutoff_status(interval, date(2026, 9, 30)) == "ambiguous_cutoff_date"
    decision = decide_work(counting_event="first_public_posting",
                           postings=[EventRecord("doi:x", "crossref", "posting", interval, "posted-content")],
                           evaluations=[], finals=[], cutoff=date(2026, 9, 30), requires_evaluation=False)
    assert decision.included is False and decision.exclusion_reason == "ambiguous_cutoff_date"
    assert decision.counting_year is None


def test_pipeline_reports_ambiguous_and_future_events(pipeline_outputs):
    out = pipeline_outputs
    works = {w["canonical_work_id"]: w for w in out.works("qeios_hosted_works")}
    # year-only posting in the cutoff year without a qualifying review: not counted
    assert works["doi:10.32388/ffff66"]["included"] == "false"
    assert works["doi:10.32388/ffff66"]["counting_year"] == ""
    # a review dated after the cutoff does not qualify a 2024 posting
    assert works["doi:10.32388/dddd44"]["included"] == "false"
    assert works["doi:10.32388/dddd44"]["exclusion_reason"] == "no_qualifying_review"
    assert works["doi:10.32388/dddd44"]["eligibility_review_event_date_raw"] == ""
    prereview = {w["canonical_work_id"]: w for w in out.works("prereview")}
    assert prereview["doi:10.1101/2024.02.02.000002"]["exclusion_reason"] == "future_event"
    # excluded works never appear in a year count
    counted = sum(int(c["count"]) for c in out.cells("works_by_row_year", row_id="qeios_hosted_works") if c["count"])
    assert counted == len([w for w in works.values() if w["included"] == "true"]) == 2


def test_nothing_counted_after_cutoff_in_any_row(pipeline_outputs):
    cutoff = pipeline_outputs.run_config.analysis_cutoff_date.isoformat()
    for w in pipeline_outputs.works():
        if w["included"] == "true":
            assert w["counting_event_interval_end"] <= cutoff, w
