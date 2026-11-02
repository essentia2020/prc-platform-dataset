"""tools/append_dq_rows.py: preset rows land after the last preset row; untouched lines keep their bytes."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from src.analyse.build_aggregates import DQ_COLUMNS
from tools import append_dq_rows

REPO_LOG = Path(__file__).resolve().parents[1] / "data" / "processed" / "data_quality_log.csv"

PRESETS = [
    ["DQ-001", "qeios_hosted_works", "deposition_discontinuity", "d1", "e1", "f1", "h1", "", "template", "preset", "", ""],
    ["DQ-002", "peerref", "source_not_covering", "d2", "e2", "f2", "h2", "", "observed", "preset", "", ""],
]
RUN_ROWS = [
    ["DQ-run_x_01-001", "f1000research", "withdrawn_record", "d", "records_f1000research.csv", "lowers the row count",
     "dropped", "3", "observed", "run", "run_x_01", "works__10.12688__posted-content=w01"],
]
NEW_A = ["DQ-003", "the_unjournal", "companion_record", "Thirteen summaries, no relation.", "probe", "none on works",
         "not in scope", "13", "observed", "preset", "", ""]
NEW_B = ["DQ-004", "review_commons", "date_semantics", "issued is the package date; text with, a comma", "sample",
         "shifts the year", "no imputation", "", "template", "preset", "", ""]


def _write_log(path: Path, rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(DQ_COLUMNS)
    writer.writerows(rows)
    path.write_bytes(buf.getvalue().encode("utf-8"))
    return path.read_bytes()


def _csv_lines(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def _ids(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [r["issue_id"] for r in csv.DictReader(handle)]


@pytest.fixture
def log(tmp_path: Path) -> Path:
    path = tmp_path / "data_quality_log.csv"
    _write_log(path, PRESETS + RUN_ROWS)
    return path


def test_rows_are_inserted_after_the_last_preset_row(log: Path, tmp_path: Path) -> None:
    before = log.read_bytes().decode("utf-8").splitlines()
    rows = tmp_path / "rows.csv"
    rows.write_text(_csv_lines([NEW_A, NEW_B]), encoding="utf-8")
    assert append_dq_rows.main([str(rows), "--log", str(log)]) == 0
    assert _ids(log) == ["DQ-001", "DQ-002", "DQ-003", "DQ-004", "DQ-run_x_01-001"]
    after = log.read_bytes().decode("utf-8").splitlines()
    assert after[:3] == before[:3] and after[-1] == before[-1]          # untouched lines keep their bytes
    assert not log.read_bytes().startswith(b"\xef\xbb\xbf") and b"\r" not in log.read_bytes()


def test_header_line_and_diff_input_are_accepted(log: Path, tmp_path: Path) -> None:
    with_header = tmp_path / "with_header.csv"
    with_header.write_text(",".join(DQ_COLUMNS) + "\n" + _csv_lines([NEW_A]), encoding="utf-8")
    assert append_dq_rows.main([str(with_header), "--log", str(log)]) == 0
    patch = tmp_path / "package.diff"
    patch.write_text("--- a/x\n+++ b/x\n@@ -1 +1,2 @@\n context\n+" + _csv_lines([NEW_B]) + "+not a row\n", encoding="utf-8")
    assert append_dq_rows.main([str(patch), "--log", str(log)]) == 0
    assert _ids(log) == ["DQ-001", "DQ-002", "DQ-003", "DQ-004", "DQ-run_x_01-001"]


def test_identical_row_is_skipped_and_a_changed_row_needs_replace(log: Path, tmp_path: Path, capsys) -> None:
    rows = tmp_path / "rows.csv"
    rows.write_text(_csv_lines([NEW_A]), encoding="utf-8")
    assert append_dq_rows.main([str(rows), "--log", str(log)]) == 0
    stamp = log.read_bytes()
    assert append_dq_rows.main([str(rows), "--log", str(log)]) == 0
    assert log.read_bytes() == stamp and "skipped 1 identical" in capsys.readouterr().out
    changed = dict(zip(DQ_COLUMNS, NEW_A))
    changed["n_records_affected"] = "14"
    rows.write_text(_csv_lines([[changed[c] for c in DQ_COLUMNS]]), encoding="utf-8")
    assert append_dq_rows.main([str(rows), "--log", str(log)]) == 1
    assert log.read_bytes() == stamp
    assert append_dq_rows.main([str(rows), "--log", str(log), "--replace"]) == 0
    with log.open(newline="", encoding="utf-8") as handle:
        assert {r["issue_id"]: r["n_records_affected"] for r in csv.DictReader(handle)}["DQ-003"] == "14"


@pytest.mark.parametrize("field, value", [
    ("issue_id", "DQ-run_x_01-009"),      # run-style identifier
    ("origin", "run"),
    ("status", "pending"),
    ("run_id", "run_x_01"),
    ("issue_type", "not_a_type"),
    ("row_id", "no_such_row"),
    ("n_records_affected", "thirteen"),
    ("handling", ""),
])
def test_invalid_rows_are_rejected_before_writing(log: Path, tmp_path: Path, field: str, value: str) -> None:
    stamp = log.read_bytes()
    row = dict(zip(DQ_COLUMNS, NEW_A))
    row[field] = value
    rows = tmp_path / "rows.csv"
    rows.write_text(_csv_lines([[row[c] for c in DQ_COLUMNS]]), encoding="utf-8")
    assert append_dq_rows.main([str(rows), "--log", str(log)]) == 1
    assert log.read_bytes() == stamp


def test_wrong_column_count_and_empty_input(log: Path, tmp_path: Path) -> None:
    stamp = log.read_bytes()
    short = tmp_path / "short.csv"
    short.write_text("DQ-005,peerref,other\n", encoding="utf-8")
    assert append_dq_rows.main([str(short), "--log", str(log)]) == 1
    empty = tmp_path / "empty.diff"
    empty.write_text("--- a/x\n+++ b/x\n+nothing here\n", encoding="utf-8")
    assert append_dq_rows.main([str(empty), "--log", str(log)]) == 2
    assert log.read_bytes() == stamp


def test_dry_run_writes_nothing(log: Path, tmp_path: Path, capsys) -> None:
    stamp = log.read_bytes()
    rows = tmp_path / "rows.csv"
    rows.write_text(_csv_lines([NEW_A]), encoding="utf-8")
    assert append_dq_rows.main([str(rows), "--log", str(log), "--dry-run"]) == 0
    assert log.read_bytes() == stamp and "would insert 1 row(s) DQ-003" in capsys.readouterr().out


def test_repository_log_round_trips_through_the_writer(tmp_path: Path) -> None:
    """The log in the repository is already in the writer's form: re-inserting an existing row changes no byte."""
    copy = tmp_path / "log.csv"
    copy.write_bytes(REPO_LOG.read_bytes())
    with REPO_LOG.open(newline="", encoding="utf-8") as handle:
        presets = [r for r in csv.DictReader(handle) if r["origin"] == "preset"]
    assert presets
    rows = tmp_path / "rows.csv"
    rows.write_text(_csv_lines([[presets[-1][c] for c in DQ_COLUMNS]]), encoding="utf-8")
    assert append_dq_rows.main([str(rows), "--log", str(copy)]) == 0
    assert copy.read_bytes() == REPO_LOG.read_bytes()


def test_issue_types_come_from_the_data_dictionary() -> None:
    types = append_dq_rows.issue_types()
    assert {"companion_record", "date_semantics", "source_not_covering", "other"} <= types
    assert "qeios_hosted_works" in append_dq_rows.register_row_ids()
