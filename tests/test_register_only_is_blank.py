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


def test_provisional_row_is_excluded_from_headline_tables(pipeline_outputs, tmp_path):
    # No register row is provisional since D-071; the gate is exercised on a copy of the register.
    from copy import deepcopy
    from src.analyse import build_aggregates
    from src.common.config import load_sources_config
    from src.common.log import JsonlLogger
    from src.common.interim import read_csv
    out = pipeline_outputs
    assert not [str(p["row_id"]) for p in out.platforms if p.get("provisional")]
    platforms = deepcopy(out.platforms)
    next(r for r in platforms if r["row_id"] == "verixiv")["provisional"] = True
    logger = JsonlLogger(out.run_config.run_id, log_dir=tmp_path / "logs")
    build_aggregates.run(out.run_config, load_sources_config(), platforms, logger, processed_root=out.processed,
                         manifest_root=out.roots["manifest_root"], tables_root=tmp_path / "tables")
    tables = tmp_path / "tables"
    assert [c for c in read_csv(tables / "works_by_row_year.csv") if c["row_id"] == "verixiv"]   # row table
    assert [c for c in read_csv(tables / "unique_works_all_rows_by_row_year.csv") if c["row_id"] == "verixiv"] == []
    summary = next(c for c in read_csv(tables / "register_summary.csv") if c["row_id"] == "verixiv")
    assert summary["provisional"] == "true"
    # evidence table carries no binding decision for a provisional row
    features = next(c for c in read_csv(tables / "evidence_features_by_platform.csv") if c["row_id"] == "verixiv")
    assert features["binding_publication_decision"] == ""
