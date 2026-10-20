"""§8.3: a complete scope with no qualifying work is zero, with observed_zero status."""


def test_complete_empty_cells_are_zero(pipeline_outputs):
    out = pipeline_outputs
    # F1000Research fixture has one work in 2022 and nothing in 2023
    cell = out.cell("works_by_row_year", row_id="f1000research", year=2023)
    assert cell["count"] == "0" and cell["observation_status"] == "observed_zero"
    assert cell["extraction_status"] == "complete" and cell["coverage"] == "complete"
    # a row whose fixture scope is complete and entirely empty is zero in range, blank before launch
    cells = {int(c["year"]): c for c in out.cells("works_by_row_year", row_id="scipost")}
    assert cells[2020]["count"] == "0" and cells[2020]["observation_status"] == "observed_zero"
    assert cells[2010]["count"] == "" and cells[2010]["observation_status"] == "not_applicable"


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
    assert cell["partial_year"] == "true" and cell["coverage"] == "year_to_date"
    assert "year_to_date" in cell["year_label"]
    assert cell["count"] == "0"      # complete scope, no 2026 qualifying work in the fixture
    for c in out.cells("works_by_row_year", year=2025):
        assert c["partial_year"] == "false"
