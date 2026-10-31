"""D-065: Review Commons counted from Crossref peer-review records (stem rc. under 10.15252).

Selector behaviour on the DOI shapes observed on 2026-10-31 (referee reports
and author responses share one stem, one type and one is-review-of target),
the fixture run (one work per reviewed preprint at the earliest report; the
author response never adds a work; 2019 is not_applicable) and the register
prefix check for member 79 (EMBO Press).
"""
from __future__ import annotations

import json

import pytest

from src.common.interim import read_csv
from src.common.register import load_platforms, platforms_by_row_id
from src.extract.selectors import compile_crossref_selector, review_targets
from tests.offline import FixtureTransport, run_full_pipeline
from tools import check_register_prefixes as prefix_check

ROW = "review_commons"


def _record(doi, record_type, targets=(), reply_to=()):
    item = {"DOI": doi, "type": record_type, "prefix": doi.split("/")[0], "member": "79"}
    relation = {}
    if targets:
        relation["is-review-of"] = [{"id": t, "id-type": "doi", "asserted-by": "subject"} for t in targets]
    if reply_to:
        relation["is-reply-to"] = [{"id": r, "id-type": "doi", "asserted-by": "subject"} for r in reply_to]
    if relation:
        item["relation"] = relation
    return item


@pytest.fixture(scope="module")
def selector():
    row = platforms_by_row_id(load_platforms())[ROW]
    return row, compile_crossref_selector(row)


# ------------------------------------------------------------------ register
def test_register_row_is_crossref_primary_with_sciety_cross_check(selector):
    row, _ = selector
    assert row["data_source"] == "both" and row["data_status"] == "machine_readable"
    assert row["extraction_selector"]["crossref"]["role"] == "primary"
    assert row["extraction_selector"]["sciety"]["role"] == "cross_check"
    assert row["extraction_selector"]["crossref"]["record_types"] == ["peer-review"]
    assert row["extraction_selector"]["crossref"]["target_filter"] == "external"
    assert row["review_to_object_relation"] == "crossref_is_review_of" and row["review_has_doi"] is True
    assert row["counting_event"] == "earliest_qualifying_evaluation"
    assert row["counting_event_date_field"] == "issued"
    # the first record is issued in 2020; the service launched in December 2019
    assert (row["launch_year"], row["model_since"], row["coverage_start_year"]) == (2019, 2019, 2020)
    assert "partial_coverage" not in json.dumps(row)


# ------------------------------------------------------------------ selector
def test_stem_reviews_with_external_targets_are_claimed(selector):
    _, sel = selector
    assert sel.review_doi_regex.pattern == r"^10\.15252/rc\."
    report = _record("10.15252/rc.2023168736", "peer-review", ["10.1101/2022.02.25.481813"])
    assert sel.claims_review(report, review_targets(report))
    assert not sel.matches_work(report)
    # case of the DOI string does not matter
    upper = _record("10.15252/RC.2023168736", "peer-review", ["10.1101/2022.02.25.481813"])
    assert sel.claims_review(upper, review_targets(upper))
    # medRxiv targets are external too
    med = _record("10.15252/rc.2024000001", "peer-review", ["10.1101/2024.01.01.24300001"])
    assert sel.claims_review(med, review_targets(med))


def test_author_response_is_a_record_of_the_row_with_the_same_target(selector):
    _, sel = selector
    response = _record("10.15252/rc.2023949760", "peer-review", ["10.1101/2022.02.25.481813"],
                       reply_to=["10.15252/rc.2023168736"])
    targets = review_targets(response)
    assert sel.claims_review(response, targets)
    assert [t.doi for t in targets] == ["10.1101/2022.02.25.481813"] and targets[0].flag == ""


def test_records_outside_the_stem_or_type_are_not_the_rows(selector):
    _, sel = selector
    # a peer-review record of the same member (EMBO Press) outside the rc. stem
    other = _record("10.15252/rpf.2023000401", "peer-review", ["10.1101/2023.01.15.000004"])
    assert not sel.claims_review(other, review_targets(other))
    assert not sel.matches_work(other)
    # the member's journal articles are neither reviews nor works of the row
    article = _record("10.15252/embj.2023113456", "journal-article")
    assert not sel.claims_review(article, review_targets(article))
    assert not sel.matches_work(article)
    # the row owns reviews, not works: no DOI is a work of the row by its own shape
    assert not sel.doi_in_scope("10.15252/rc.2023168736") and not sel.doi_in_scope("10.1101/2022.02.25.481813")


# --------------------------------------------------------------- fixture run
@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    return run_full_pipeline(tmp_path_factory.mktemp("d065"), transport=FixtureTransport(scripted={}))


def test_one_work_per_preprint_at_the_earliest_report(outputs):
    # fixture: preprint A (two reports + response, 2020-05-10), preprint B (report 2021-07-01, revision-round
    # report + response 2022-02-14), preprint C (one report 2023-02-01), one report after the cutoff
    works = {w["canonical_work_id"]: w for w in outputs.works(ROW) if w["counting_year"]}
    assert set(works) == {"doi:10.1101/2020.03.01.000001", "doi:10.1101/2021.06.01.000002",
                          "doi:10.1101/2023.01.01.23000003"}
    assert works["doi:10.1101/2021.06.01.000002"]["counting_event_date_raw"] == "2021-07-01"
    for year, count in ((2020, "1"), (2021, "1"), (2022, "0"), (2023, "1"), (2024, "0"), (2025, "0"), (2026, "0")):
        cell = outputs.cell("works_by_row_year", row_id=ROW, year=year)
        assert cell["count"] == count, year
        assert cell["observation_status"] == ("observed" if count != "0" else "observed_zero")
        assert cell["coverage"] == ("year_to_date" if year == 2026 else "complete")
        assert cell["source_observability_status"] == "observable"


def test_years_before_coverage_start_are_not_applicable(outputs):
    for year in (2018, 2019):
        cell = outputs.cell("works_by_row_year", row_id=ROW, year=year)
        assert cell["count"] == "" and cell["observation_status"] == "not_applicable"
    row = outputs.analysis_manifest["rows"][ROW]
    assert row["eligible_start"] == 2020


def test_author_responses_and_off_stem_records_never_add_a_work(outputs):
    row = outputs.analysis_manifest["rows"][ROW]
    diag = row["diagnostics"]
    # 9 fixture items: 8 under the stem (5 reports, 2 responses, 1 post-cutoff report), 1 outside the stem
    assert diag["n_evaluation_records"] == 8 and diag["n_work_records"] == 0
    assert diag["n_relations_flagged"] == 0 and diag["excluded_future_event"] == 1
    assert diag["n_included"] == 3
    records = outputs.records(ROW)
    dois = {r["source_record_id"].lower() for r in records if r["source_record_id"]}
    assert "10.15252/rpf.2023000401" not in dois
    assert {"10.15252/rc.2020000103", "10.15252/rc.2022000203"} <= dois        # author responses kept as records


def test_row_is_observable_and_the_sciety_group_is_a_cross_check(outputs):
    row = outputs.analysis_manifest["rows"][ROW]
    assert row["extraction_status"] == "complete"
    assert row["source_not_covering"] is False and row["selector_no_match"] is False
    assert row["index_coverage"] == {"sciety/evaluations__review-commons": "not_in_index"}
    assert row["cross_check_scopes"] == {"sciety/evaluations__review-commons": "complete"}
    dq = [r for r in read_csv(outputs.processed / "data_quality_log.csv") if r["row_id"] == ROW]
    assert not [r for r in dq if r["issue_type"] == "source_not_covering"]
    summary = next(r for r in outputs.table("register_summary") if r["row_id"] == ROW)
    assert summary["unique_works_to_cutoff"] == "3"


def test_group_cells_count_the_row_instead_of_excluding_it(outputs):
    for year in (2020, 2021, 2023):
        for table, where in (("works_by_class_year", {"initiation_class": "author_initiated"}),
                             ("works_by_configuration_year", {"prc_configuration": "review_or_curation_service"})):
            cell = outputs.cell(table, year=year, **where)
            assert f"{ROW}:source_not_covering" not in cell["excluded_rows"]
            assert ROW not in cell["lower_bound_rows"]


# ------------------------------------------------------------ prefix check
class _Resolver:
    def __init__(self, records):
        self.records = records

    def __call__(self, url, headers, timeout):
        from urllib.parse import unquote
        doi = unquote(url.split("/works/", 1)[1].split("?", 1)[0]).lower()
        rec = self.records.get(doi)
        if rec is None:
            return 404, {}, b"Resource not found."
        return 200, {}, json.dumps({"status": "ok", "message": rec}).encode()


def test_prefix_check_expectations_for_member_79():
    rows = load_platforms()
    records = {"10.15252/rc.2023168736": {"prefix": "10.15252", "member": "79", "type": "peer-review"}}
    results = prefix_check.run_check(rows, _Resolver(records), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", only={ROW}, sleep=lambda s: None)
    (result,) = results
    checks = {c.role: c for c in result.checks}
    assert result.status == "ok"
    assert checks["review"].status == "ok" and checks["review"].member == "79"
    assert checks["review"].owner_prefix == "10.15252" and "10.15252" in checks["review"].declared
    assert checks["work"].status == "not_applicable"
    assert prefix_check.exit_code(results) == 0
