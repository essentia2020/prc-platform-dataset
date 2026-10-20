"""D-040: one data-quality log; preset rows untouched; run rows carry run_id, walk_id, origin."""

import csv
from pathlib import Path

from src.analyse.build_aggregates import DQ_COLUMNS

REPO_LOG = Path(__file__).resolve().parents[1] / "data" / "processed" / "data_quality_log.csv"


def _rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_preset_rows_are_never_modified(pipeline_outputs):
    before = _rows(REPO_LOG)
    after = _rows(pipeline_outputs.processed / "data_quality_log.csv")
    assert list(after[0].keys()) == DQ_COLUMNS
    presets = [r for r in after if r["origin"] == "preset"]
    assert presets == before
    assert all(r["origin"] == "preset" and r["run_id"] == "" and r["walk_id"] == "" for r in before)


def test_run_rows_carry_run_identity(pipeline_outputs):
    after = _rows(pipeline_outputs.processed / "data_quality_log.csv")
    run_rows = [r for r in after if r["origin"] == "run"]
    assert run_rows
    run_id = pipeline_outputs.run_config.run_id
    for r in run_rows:
        assert r["run_id"] == run_id and r["walk_id"] and r["status"] == "observed"
        assert r["issue_id"].startswith(f"DQ-{run_id}-") and int(r["n_records_affected"]) > 0
    types = {(r["row_id"], r["issue_type"]) for r in run_rows}
    assert ("qeios_hosted_works", "withdrawn_record") in types
    assert ("copernicus_interactive_public_peer_review", "partial_source_coverage") in types
    assert ("qeios_external_works", "placeholder_relation") not in types     # flagged reviews stay unattributed
