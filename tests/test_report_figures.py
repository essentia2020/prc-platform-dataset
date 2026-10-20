"""Stage 6: figures are produced from tables only; categorical panels; checksums."""

import hashlib
from pathlib import Path

import pytest

from src.report.make_reports import (COVERAGE_COLOURS, IDENTITY_COLOURS, TRI_STATE_COLOURS, category_colour_map,
                                     write_checksums)

matplotlib = pytest.importorskip("matplotlib")


def test_all_seven_figures_exist_in_both_formats(pipeline_outputs):
    names = sorted(p.stem for p in pipeline_outputs.figures.glob("*.png"))
    assert [n.split("_")[0] for n in names] == [f"fig{i}" for i in range(1, 8)]
    for name in names:
        assert (pipeline_outputs.figures / f"{name}.svg").exists()
        assert (pipeline_outputs.figures / f"{name}.png").stat().st_size > 0


def test_footer_mentions_cutoff_and_year_to_date(pipeline_outputs):
    svg = (pipeline_outputs.figures / "fig2_unique_works_by_class.svg").read_text(encoding="utf-8")
    assert "2026-09-30" in svg and "year_to_date" in svg and "not annualised" in svg


def test_categorical_colour_maps_are_distinct_and_non_ordinal():
    cmap = category_colour_map(["a", "b", "c", "d"])
    assert len(set(cmap.values())) == 4
    assert set(TRI_STATE_COLOURS) == {"true", "false", "unknown"}
    assert set(IDENTITY_COLOURS) == {"always", "optional", "never", "unknown"}
    assert len(set(TRI_STATE_COLOURS.values())) == 3 and len(set(IDENTITY_COLOURS.values())) == 4
    assert "register_only" in COVERAGE_COLOURS and "partial_known_scope" in COVERAGE_COLOURS


def test_figure_7_has_two_panels_with_separate_legends(pipeline_outputs):
    svg = (pipeline_outputs.figures / "fig7_recognition_signals.svg").read_text(encoding="utf-8")
    assert "Panel A" in svg and "Panel B" in svg
    assert "Panel A legend" in svg and "Panel B legend" in svg
    assert "reviewer_identity_disclosed" in svg


def test_checksums_cover_processed_tables_and_figures(pipeline_outputs):
    out = pipeline_outputs
    lines = out.checksums.read_text(encoding="utf-8").splitlines()
    listed = {line.split("  ", 1)[1] for line in lines}
    expected = {p.as_posix() for root in (out.processed, out.tables, out.figures) for p in root.rglob("*") if p.is_file()}
    assert listed == expected
    sample = next(l for l in lines if l.endswith("works_included.csv"))
    digest, path = sample.split("  ", 1)
    assert digest == hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_checksums_skip_self_and_gitkeep(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / ".gitkeep").write_text("")
    target = tmp_path / "CHECKSUMS.txt"
    assert write_checksums(target, [tmp_path]) == 1
    assert "a.txt" in target.read_text() and "gitkeep" not in target.read_text()
