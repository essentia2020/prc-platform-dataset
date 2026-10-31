"""D-040: one data-quality log; preset rows untouched; run rows carry run_id, walk_id, origin."""

import csv
from pathlib import Path

from src.analyse.build_aggregates import DQ_COLUMNS

REPO_LOG = Path(__file__).resolve().parents[1] / "data" / "processed" / "data_quality_log.csv"


def _rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_preset_rows_are_never_modified(pipeline_outputs):
    before = [r for r in _rows(REPO_LOG) if r["origin"] == "preset"]
    after = _rows(pipeline_outputs.processed / "data_quality_log.csv")
    assert list(after[0].keys()) == DQ_COLUMNS
    presets = [r for r in after if r["origin"] == "preset"]
    assert presets == before


def test_run_rows_carry_run_identity(pipeline_outputs):
    after = _rows(pipeline_outputs.processed / "data_quality_log.csv")
    run_id = pipeline_outputs.run_config.run_id
    own = [r for r in after if r["origin"] == "run" and r["run_id"] == run_id]
    foreign = [r for r in after if r["origin"] == "run" and r["run_id"] != run_id]
    assert own
    for r in own + foreign:
        assert r["run_id"] and r["walk_id"] and r["status"] == "observed"

def test_fixture_log_is_seeded_with_preset_rows_only(pipeline_outputs):
    """D-061, defect 3: rows of real runs in the repository log never reach the offline fixture."""
    after = _rows(pipeline_outputs.processed / "data_quality_log.csv")
    run_id = pipeline_outputs.run_config.run_id
    foreign = [r for r in after if r["origin"] == "run" and r["run_id"] != run_id]
    assert foreign == []
    assert {r["run_id"] for r in after} <= {"", run_id}
    repo_run_rows = [r for r in _rows(REPO_LOG) if r["origin"] == "run"]
    if repo_run_rows:  # the working-tree log may carry rows of a real run
        assert not {r["issue_id"] for r in repo_run_rows} & {r["issue_id"] for r in after}
