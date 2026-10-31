"""Stage 6: figures are produced from tables only; categorical panels; checksums."""

import csv
import hashlib
from datetime import date
from pathlib import Path

import pytest

from src.report import make_reports
from src.report.make_reports import (COVERAGE_COLOURS, FIG8_OTHER_COLOUR, FIG8_OTHER_LABEL, FIG8_OTHER_THRESHOLD,
                                     IDENTITY_COLOURS, TRI_STATE_COLOURS, category_colour_map, figure_8_series,
                                     write_checksums)

matplotlib = pytest.importorskip("matplotlib")


def test_all_eight_figures_exist_in_both_formats(pipeline_outputs):
    names = sorted(p.stem for p in pipeline_outputs.figures.glob("*.png"))
    assert [n.split("_")[0] for n in names] == [f"fig{i}" for i in range(1, 9)]
    for name in names:
        assert (pipeline_outputs.figures / f"{name}.svg").exists()
        assert (pipeline_outputs.figures / f"{name}.png").stat().st_size > 0


def test_footer_mentions_cutoff_and_year_to_date(pipeline_outputs):
    svg = (pipeline_outputs.figures / "fig2_unique_works_by_class.svg").read_text(encoding="utf-8")
    assert "2026-09-30" in svg and "year_to_date" in svg and "not annualised" in svg


def test_lower_bound_cells_are_named_in_the_figure_footer(pipeline_outputs):
    """D-061: figures 2, 3, 6 name the rows behind lower-bound cells once, deduplicated across years."""
    fig2 = (pipeline_outputs.figures / "fig2_unique_works_by_class.svg").read_text(encoding="utf-8")
    assert "lower bounds (D-061)" in fig2
    assert fig2.count("qeios_external_works") == 1 and "prereview" in fig2
    assert "prelights" in fig2            # excluded (source_not_covering) rows are named too
    fig6 = (pipeline_outputs.figures / "fig6_unique_works_by_configuration.svg").read_text(encoding="utf-8")
    assert "lower bounds (D-061)" in fig6
    # figure 3 draws only years with a published all-rows total; none in the fixture, so no sentence
    fig3 = (pipeline_outputs.figures / "fig3_class_shares.svg").read_text(encoding="utf-8")
    assert "Attribution to a class is relative" in fig3


def test_svg_ids_are_salted_with_the_run_id(pipeline_outputs):
    """D-059 (merged into D-061): ``svg.hashsalt`` is the run_id, so unchanged tables give identical SVGs."""
    assert matplotlib.rcParams["svg.hashsalt"] == pipeline_outputs.run_config.run_id
    svg = (pipeline_outputs.figures / "fig2_unique_works_by_class.svg").read_text(encoding="utf-8")
    assert "<dc:date>" not in svg


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


# ------------------------------------------------- figure layout rules (synthetic tables)
CUTOFF = date(2026, 9, 30)


def _write(path: Path, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in keys})


def _cell(year, count, **extra):
    base = {"year": str(year), "year_label": str(year), "count": "" if count is None else str(count),
            "partial_year": "true" if year == CUTOFF.year else "false",
            "blocking_rows": "", "lower_bound_rows": "", "excluded_rows": ""}
    base.update({k: str(v) for k, v in extra.items()})
    return base


@pytest.fixture
def captured(monkeypatch):
    """Keep the figure objects instead of saving them, so that axes, legends and titles can be inspected."""
    figures = {}

    def fake_save(fig, figures_root, name):
        fig.canvas.draw()
        figures[name] = fig
        return []
    monkeypatch.setattr(make_reports, "_save", fake_save)
    return figures


@pytest.fixture
def synthetic_tables(tmp_path):
    tables = tmp_path / "tables"
    tables.mkdir()
    # Figure 6 input: one configuration in the thousands, one in the tens, one blank, one lower bound
    config_rows = []
    for year in range(2019, 2027):
        config_rows.append(dict(_cell(year, 1000 + 500 * (year - 2019)), prc_configuration="approval_threshold"))
        config_rows.append(dict(_cell(year, 10 + year - 2019, lower_bound_rows="prereview:partial_coverage"),
                                prc_configuration="review_or_curation_service"))
        config_rows.append(dict(_cell(year, 3000 + 300 * (year - 2019)), prc_configuration="hybrid_public_discussion"))
        config_rows.append(dict(_cell(year, None, blocking_rows="scipost:selector_no_match"),
                                prc_configuration="core_publish_first"))
    _write(tables / "unique_works_by_configuration_year.csv", config_rows)
    class_rows = []
    for year in range(2001, 2027):
        class_rows.append(dict(_cell(year, 100 * (year - 2000)), initiation_class="author_initiated"))
        class_rows.append(dict(_cell(year, 5 if year >= 2018 else None, lower_bound_rows="prereview:partial_coverage"),
                               initiation_class="community_initiated"))
    _write(tables / "unique_works_by_class_year.csv", class_rows)
    # all-rows table: published 2001–2026, blank 2010, lower bound from 2018
    all_rows = []
    for year in range(2001, 2027):
        if year == 2010:
            all_rows.append(_cell(year, None, blocking_rows="scipost:selector_no_match"))
            continue
        total = 100 * (year - 2000) + (5 if year >= 2018 else 0)
        all_rows.append(_cell(year, total, n_author_initiated_by_earliest_event=100 * (year - 2000),
                              n_community_initiated_by_earliest_event=5 if year >= 2018 else 0,
                              n_mixed_by_earliest_event=0,
                              lower_bound_rows="prereview:partial_coverage" if year >= 2018 else "",
                              excluded_rows="peerref:source_not_covering" if year >= 2018 else ""))
    _write(tables / "unique_works_all_rows_year.csv", all_rows)
    # by-row table: a big row, a middle row, three small rows (merged into Other), one row blank throughout,
    # and a row with a count in the blank year 2010 only (never drawn)
    by_row = []
    for year in range(2001, 2027):
        if year == 2010:
            by_row.append(dict(_cell(year, 7), row_id="only_in_blank_year"))
            continue
        total = 100 * (year - 2000) + (5 if year >= 2018 else 0)
        small = [1, 2, 2] if year >= 2018 else [0, 0, 0]
        by_row.append(dict(_cell(year, total - 30 - sum(small)), row_id="copernicus_interactive_public_peer_review"))
        by_row.append(dict(_cell(year, 30), row_id="meded_publish"))      # 30 × 25 years = 750 < threshold
        for rid, v in zip(("prereview", "tiny_a", "tiny_b"), small):
            by_row.append(dict(_cell(year, v if v else None), row_id=rid))
        by_row.append(dict(_cell(year, None), row_id="never_counted"))
    _write(tables / "unique_works_all_rows_by_row_year.csv", by_row)
    return tables


def _legend_patches(fig):
    patches = []
    for ax in fig.axes:
        legend = ax.get_legend()
        if legend is not None:
            patches.extend(legend.get_patches())
    for legend in fig.legends:
        patches.extend(legend.get_patches())
    return patches


def test_figure_6_panels_keep_their_own_maximum_in_view(synthetic_tables, captured):
    make_reports.figure_6(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    fig = captured["fig6_unique_works_by_configuration"]
    drawn = [ax for ax in fig.axes if ax.patches]
    assert len(drawn) == 3                                      # the blank configuration has no panel content
    for ax in drawn:
        top = max(p.get_height() for p in ax.patches)
        assert ax.get_ylim()[1] >= top, ax.get_title()
    tops = {ax.get_title(): ax.get_ylim()[1] for ax in drawn}
    assert tops["review_or_curation_service"] < 100 < tops["approval_threshold"] < tops["hybrid_public_discussion"]
    assert not any(ax.get_shared_y_axes().joined(ax, other) for ax in drawn for other in drawn if other is not ax)


def test_figure_3_legend_sits_outside_the_axes(synthetic_tables, captured):
    make_reports.figure_3(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    fig = captured["fig3_class_shares"]
    ax = fig.axes[0]
    renderer = fig.canvas.get_renderer()
    legend_box = ax.get_legend().get_window_extent(renderer)
    axes_box = ax.get_window_extent(renderer)
    assert legend_box.x0 >= axes_box.x1                       # entirely to the right of the plotting area
    assert ax.get_ylim() == (0.0, 1.0)


def test_legend_handles_carry_no_hatch(synthetic_tables, captured, pipeline_outputs):
    make_reports.figure_2(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    make_reports.figure_3(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    make_reports.figure_8(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    make_reports.figure_5(pipeline_outputs.tables, CUTOFF, "snap", synthetic_tables)
    assert set(captured) == {"fig2_unique_works_by_class", "fig3_class_shares", "fig8_unique_works_by_row_stacked",
                             "fig5_qeios_indicators"}
    for name, fig in captured.items():
        patches = _legend_patches(fig)
        assert patches, name
        assert all(not p.get_hatch() for p in patches), name
        # while the bars themselves are hatched where the cell says so
        assert any(p.get_hatch() for ax in fig.axes for p in ax.patches), name


def test_suptitle_sits_directly_above_the_axes(synthetic_tables, captured):
    make_reports.figure_2(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    make_reports.figure_3(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    for name, fig in captured.items():
        renderer = fig.canvas.get_renderer()
        inv = fig.transFigure.inverted()
        top = max(inv.transform((0, ax.get_tightbbox(renderer).y1))[1] for ax in fig.axes)
        title_y = inv.transform((0, fig._suptitle.get_window_extent(renderer).y0))[1]
        assert 0 <= title_y - top <= 0.04, name


# ------------------------------------------------------------------------ Figure 8
def test_figure_8_segments_sum_to_the_all_rows_total(synthetic_tables):
    data = figure_8_series(synthetic_tables)
    assert 2010 not in data["years"] and len(data["years"]) == 25        # blank all-rows year not drawn
    for year in data["years"]:
        assert sum(seg.get(year, 0) for seg in data["segments"].values()) == data["totals"][year]
    assert "only_in_blank_year" not in data["order"] and "only_in_blank_year" not in data["other_rows"]
    assert "never_counted" not in data["order"] and "never_counted" not in data["other_rows"]


def test_figure_8_other_holds_only_rows_below_the_threshold_and_sorts_by_total(synthetic_tables):
    data = figure_8_series(synthetic_tables)
    totals = {}
    for r in make_reports._read(synthetic_tables / "unique_works_all_rows_by_row_year.csv"):
        if r["count"] and int(r["year"]) in data["years"]:
            totals[r["row_id"]] = totals.get(r["row_id"], 0) + int(r["count"])
    assert all(totals[rid] < FIG8_OTHER_THRESHOLD for rid in data["other_rows"])
    assert all(totals[label] >= FIG8_OTHER_THRESHOLD for label in data["order"] if label != FIG8_OTHER_LABEL)
    assert data["order"] == ["copernicus_interactive_public_peer_review", FIG8_OTHER_LABEL]
    assert data["other_rows"] == ["meded_publish", "tiny_a", "tiny_b", "prereview"]      # descending total, then id
    assert data["hatches"][2026] == "//.." and data["hatches"][2018] == ".." and data["hatches"][2005] == ""


def test_figure_8_draws_the_stack_with_plain_legend_and_year_hatches(synthetic_tables, captured):
    make_reports.figure_8(synthetic_tables, CUTOFF, "snap", synthetic_tables)
    fig = captured["fig8_unique_works_by_row_stacked"]
    ax = fig.axes[0]
    data = figure_8_series(synthetic_tables)
    by_year = {}
    for p in ax.patches:
        year = round(p.get_x() + p.get_width() / 2)
        by_year.setdefault(year, []).append(p)
    assert set(by_year) == set(data["years"])
    for year, patches in by_year.items():
        assert sum(p.get_height() for p in patches) == data["totals"][year]
        assert {p.get_hatch() or "" for p in patches} == {data["hatches"][year]}   # one hatch per year
        assert max(p.get_y() + p.get_height() for p in patches) <= ax.get_ylim()[1]
    legend = ax.get_legend()
    labels = [t.get_text() for t in legend.get_texts()]
    assert labels == data["order"] and labels[-1] == FIG8_OTHER_LABEL
    other_patch = legend.get_patches()[-1]
    assert matplotlib.colors.to_hex(other_patch.get_facecolor()) == FIG8_OTHER_COLOUR
    assert all(not p.get_hatch() for p in legend.get_patches())
    # the lowest segment of every year is the largest row
    for year, patches in by_year.items():
        lowest = min(patches, key=lambda p: p.get_y())
        assert matplotlib.colors.to_hex(lowest.get_facecolor()) != FIG8_OTHER_COLOUR
    footer = [t.get_text() for t in fig.texts if "Other (rows below" in t.get_text()]
    assert footer and "meded_publish" in footer[0] and "earliest counting event" in footer[0]
    assert "lower bounds (D-061)" in footer[0] and "prereview" in footer[0]
