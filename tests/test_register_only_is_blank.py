"""§8.3 gate: register-only rows publish no count — blank, never zero."""


def test_register_only_rows_are_blank_in_every_table(pipeline_outputs):
    out = pipeline_outputs
    register_only = [str(p["row_id"]) for p in out.platforms if p["register_status"] == "register_only"]
    assert register_only
    for row_id in register_only:
        cells = out.cells("works_by_row_year", row_id=row_id)
        assert cells and all(c["count"] == "" for c in cells)
        assert all(c["observation_status"] == "register_only" for c in cells)
        assert all(c["extraction_status"] == "not_applicable" for c in cells if row_id != "verixiv")
        summary = out.cell("register_summary", row_id=row_id)
        assert summary["unique_works_to_cutoff"] == "" and summary["first_year_with_data"] == ""
    # provisional and register-only rows never enter the headline group tables
    for name in ("works_by_class_year", "unique_works_by_class_year"):
        for r in out.table(name):
            assert r.get("row_id") is None


def test_provisional_row_is_excluded_from_headline_tables(pipeline_outputs):
    out = pipeline_outputs
    provisional = [str(p["row_id"]) for p in out.platforms if p.get("provisional")]
    assert "verixiv" in provisional
    assert out.cells("works_by_row_year", row_id="verixiv")          # present in the row table
    assert out.cell("register_summary", row_id="verixiv")["provisional"] == "true"
    # evidence table carries no binding decision for a provisional row
    assert out.cell("evidence_features_by_platform", row_id="verixiv")["binding_publication_decision"] == ""
