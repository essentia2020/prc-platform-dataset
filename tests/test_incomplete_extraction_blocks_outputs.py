"""§9.4/§9.7: an incomplete or failed scope blanks every dependent row, nothing else."""


def test_failed_scope_blanks_dependent_rows_only(blocked_pipeline_outputs):
    out = blocked_pipeline_outputs
    for row_id in ("f1000research", "gates_open_research", "wellcome_open_research"):
        cells = [c for c in out.cells("works_by_row_year", row_id=row_id) if c["observation_status"] != "not_applicable"]
        assert cells and all(c["count"] == "" for c in cells)
        assert all(c["observation_status"] == "not_observable" for c in cells)
        assert all(c["extraction_status"] == "failed" for c in cells)
        assert out.cell("register_summary", row_id=row_id)["unique_works_to_cutoff"] == ""
        assert out.works(row_id) == []
    # an unrelated complete row keeps its counts
    assert out.cell("works_by_row_year", row_id="qeios_hosted_works", year=2024)["count"] == "1"


def test_blocked_row_blanks_its_group_cells(blocked_pipeline_outputs):
    out = blocked_pipeline_outputs
    cls = next(p["initiation_class"] for p in out.platforms if p["row_id"] == "f1000research")
    for year in (2022, 2023, 2024):
        cell = out.cell("works_by_class_year", initiation_class=cls, year=year)
        assert cell["count"] == "" and cell["observation_status"] == "not_observable"
        assert cell["extraction_status"] == "incomplete"
        assert "f1000research:failed" in cell["blocking_rows"]
    # the all-rows deduplicated total is blank for those years too
    assert out.cell("unique_works_all_rows_year", year=2023)["count"] == ""


def test_coverage_matrix_marks_no_data_for_blocked_rows(blocked_pipeline_outputs):
    out = blocked_pipeline_outputs
    cells = [c for c in out.cells("coverage_matrix", row_id="f1000research") if int(c["year"]) >= 2013]
    assert cells and all(c["coverage"] == "no_data" for c in cells)
