"""§8.3: a complete scope with records but no qualifying work in a year is zero (observed_zero);
a complete scope that matched *no record at all* is a selector defect, never a zero (D-047)."""

from src.common.interim import read_csv


def test_complete_empty_cells_are_zero(pipeline_outputs):
    out = pipeline_outputs
    # F1000Research fixture has one work in 2022 and nothing in 2023
    cell = out.cell("works_by_row_year", row_id="f1000research", year=2023)
    assert cell["count"] == "0" and cell["observation_status"] == "observed_zero"
    assert cell["extraction_status"] == "complete" and cell["coverage"] == "complete"
    # blank before launch regardless of the selector outcome
    cells = {int(c["year"]): c for c in out.cells("works_by_row_year", row_id="scipost")}
    assert cells[2010]["count"] == "" and cells[2010]["observation_status"] == "not_applicable"


def test_selector_matching_no_record_is_never_observed_zero(pipeline_outputs):
    """D-047 guard (run_20261026_01: nihr_open_research under the wrong owner prefix)."""
    out = pipeline_outputs
    # the SciPost fixture scope is complete and returns no record of the row
    cells = {int(c["year"]): c for c in out.cells("works_by_row_year", row_id="scipost")}
    in_range = [c for y, c in cells.items() if y >= 2020]
    assert in_range and all(c["count"] == "" for c in in_range)
    assert all(c["observation_status"] == "not_observable" for c in in_range)
    assert all(c["source_observability_status"] == "selector_no_match" for c in in_range)
    assert all(c["extraction_status"] == "complete" for c in in_range)
    summary = out.cell("register_summary", row_id="scipost")
    assert summary["unique_works_to_cutoff"] == "" and summary["extraction_status"] == "complete"
    assert out.analysis_manifest["rows"]["scipost"]["selector_no_match"] is True
    dq = [r for r in read_csv(out.processed / "data_quality_log.csv")
          if r["row_id"] == "scipost" and r["issue_type"] == "selector_no_match"]
    assert len(dq) == 1 and dq[0]["n_records_affected"] == "1"
    # a group that contains the row publishes no sum for those years
    scipost_class = next(p for p in out.platforms if p["row_id"] == "scipost")["initiation_class"]
    for c in out.cells("works_by_class_year", initiation_class=scipost_class):
        if int(c["year"]) >= 2020:
            assert c["count"] == "" and c["observation_status"] == "not_observable"
            assert "scipost:selector_no_match" in c["blocking_rows"]


def test_unresolved_coverage_start_is_never_zero_filled(pipeline_outputs):
    out = pipeline_outputs
    cells = [c for c in out.cells("works_by_row_year", row_id="access_microbiology") if int(c["year"]) >= 2019]
    assert cells and all(c["count"] == "" for c in cells)
    assert all(c["observation_status"] == "not_observable" for c in cells)
    assert all(c["source_observability_status"] == "unknown_scope" for c in cells)
    assert all(c["extraction_status"] == "complete" for c in cells)
    note = out.cell("coverage_matrix", row_id="access_microbiology", year=2024)["note"]
    assert "unresolved" in note
    assert out.analysis_manifest["rows"]["access_microbiology"]["start_unresolved"] is True


def test_cutoff_year_is_year_to_date_not_annualised(pipeline_outputs):
    out = pipeline_outputs
    cell = out.cell("works_by_row_year", row_id="qeios_hosted_works", year=2026)
    # D-061 (defect 2): a partial_coverage row keeps its coverage status in the cutoff year;
    # partial_year and year_label carry the year-to-date fact.
    assert cell["partial_year"] == "true" and cell["coverage"] == "partial_coverage"
    assert "year_to_date" in cell["year_label"]
    assert cell["count"] == "0"      # complete scope, no 2026 qualifying work in the fixture
    complete_row = out.cell("works_by_row_year", row_id="f1000research", year=2026)
    assert complete_row["partial_year"] == "true" and complete_row["coverage"] == "year_to_date"
    for c in out.cells("works_by_row_year", year=2025):
        assert c["partial_year"] == "false"
