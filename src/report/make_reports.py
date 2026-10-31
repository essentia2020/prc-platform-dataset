"""Stage 6 — figures and the checksum list.

Every figure is recomputed from ``reports/tables/*.csv`` and
``config/platforms.csv`` written by Stage 5; nothing is hard-coded.  Output:
``reports/figures/fig<N>_<slug>.png`` (300 dpi) and ``.svg``, plus
``reports/CHECKSUMS.txt`` with the SHA-256 of every processed file, table
and figure.

Conventions shared by all figures:

* the analysis cutoff and snapshot date appear in every footer; group cells
  published as a lower bound (D-061) are drawn with a dotted hatch and the
  footer names the rows behind them; the cutoff
  year is drawn with hatched bars and labelled ``year_to_date`` unless the
  cutoff is 31 December;
* empty cells (``count`` blank) are never drawn as zero — they are left out
  and the legend says so;
* colours come from a colour-blind-safe categorical palette (the seaborn
  ``colorblind`` palette when seaborn is importable, the same eight hex
  values otherwise); categorical variables in Figure 7 use categorical
  colour maps and separate legends, never an ordinal encoding.

matplotlib is required for this stage only (``requirements.txt``); the
pipeline's other stages and the test suite's non-figure tests do not import
it.
"""

from __future__ import annotations

import csv
import hashlib
import textwrap
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..analyse.build_aggregates import DEFAULT_TABLES_ROOT, RECOGNITION_SIGNALS
from ..common.config import RunConfig
from ..normalise.clean_and_normalise import DEFAULT_PROCESSED_ROOT

DEFAULT_FIGURES_ROOT = Path("reports") / "figures"
DEFAULT_CHECKSUMS_PATH = Path("reports") / "CHECKSUMS.txt"

# seaborn "colorblind" palette (identical values are used when seaborn is absent)
COLORBLIND_HEX = ["#0173b2", "#de8f05", "#029e73", "#d55e00", "#cc78bc", "#ca9161", "#fbafe4", "#949494",
                  "#ece133", "#56b4e9"]
TRI_STATE_COLOURS = {"true": "#029e73", "false": "#d55e00", "unknown": "#949494"}
IDENTITY_COLOURS = {"always": "#0173b2", "optional": "#de8f05", "never": "#cc78bc", "unknown": "#949494"}
COVERAGE_COLOURS = {"complete": "#0173b2", "year_to_date": "#56b4e9", "partial_coverage": "#de8f05",
                    "partial_known_scope": "#ca9161", "no_data": "#949494", "not_applicable": "#eeeeee",
                    "register_only": "#ffffff"}
CLASS_ORDER = ["author_initiated", "community_initiated", "mixed"]
CONFIG_ORDER = ["core_publish_first", "approval_threshold", "hybrid_public_discussion", "review_or_curation_service"]


class ReportError(RuntimeError):
    pass


def palette(n: int) -> list[str]:
    try:  # pragma: no cover - optional dependency
        import seaborn as sns  # type: ignore
        return [sns.utils.rgb2hex(c) if hasattr(sns.utils, "rgb2hex") else c for c in sns.color_palette("colorblind", n)]
    except Exception:
        return [COLORBLIND_HEX[i % len(COLORBLIND_HEX)] for i in range(n)]


def category_colour_map(categories: Iterable[str], fixed: Mapping[str, str] | None = None) -> dict[str, str]:
    """Distinct colour per category; categories are never mapped to numbers."""
    cats = list(dict.fromkeys(categories))
    out: dict[str, str] = {}
    spare = [c for c in palette(len(cats) + len(fixed or {})) if c not in (fixed or {}).values()]
    for cat in cats:
        if fixed and cat in fixed:
            out[cat] = fixed[cat]
        else:
            out[cat] = spare.pop(0)
    return out


# ------------------------------------------------------------------ helpers
def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ReportError(f"missing table {path}; run the analysis stage first")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _count(value: str) -> int | None:
    return int(value) if value not in ("", None) else None


FOOTER_FONTSIZE = 7


def _footer(fig, cutoff: date, snapshot: str, extra: str = "") -> float:
    partial = not (cutoff.month == 12 and cutoff.day == 31)
    text = f"Source: Crossref and Sciety via this repository's pipeline; snapshot {snapshot or 'n/a'}; " \
           f"analysis cutoff {cutoff.isoformat()}"
    if partial:
        text += f"; {cutoff.year} is year_to_date (hatched), not annualised"
    text += ". Blank cells are not drawn (not zero)."
    if extra:
        text += " " + extra
    # wrap deterministically (D-061: footers may name many rows) and return the figure fraction the footer
    # occupies, so that callers reserve it in ``tight_layout``
    width_in, height_in = fig.get_size_inches()
    lines = textwrap.wrap(text, width=max(40, int(width_in * 72 / (FOOTER_FONTSIZE * 0.52))))
    fig.text(0.01, 0.005, "\n".join(lines), fontsize=FOOTER_FONTSIZE, ha="left", va="bottom", linespacing=1.25)
    return 0.01 + len(lines) * FOOTER_FONTSIZE * 1.25 / 72 / height_in


def _save(fig, figures_root: Path, name: str) -> list[Path]:
    figures_root.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("png", "svg"):
        path = figures_root / f"{name}.{ext}"
        fig.savefig(path, dpi=300 if ext == "png" else None, metadata={"Date": None} if ext == "svg" else None,
                    bbox_inches="tight")
        paths.append(path)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return paths


LOWER_BOUND_HATCH = ".."      # D-061: group cell published as a lower bound (named rows in the table footnote)


def _is_lower_bound(r: Mapping[str, str]) -> bool:
    return bool(r.get("lower_bound_rows") or r.get("excluded_rows"))


def _hatch(r: Mapping[str, str]) -> str:
    return ("//" if r.get("partial_year") == "true" else "") + (LOWER_BOUND_HATCH if _is_lower_bound(r) else "")


def _lower_bound_note(rows: list[dict[str, str]]) -> str:
    """One footer sentence naming the rows behind lower-bound cells, deduplicated across years (D-061)."""
    drawn = [r for r in rows if _count(r.get("count", "")) is not None]
    partial = sorted({e.split(":", 1)[0] for r in drawn for e in (r.get("lower_bound_rows") or "").split("; ") if e})
    excluded = sorted({e.split(":", 1)[0] for r in drawn for e in (r.get("excluded_rows") or "").split("; ") if e})
    if not partial and not excluded:
        return ""
    parts = []
    if partial:
        parts.append("rows with partial coverage contribute: " + ", ".join(partial))
    if excluded:
        parts.append("rows whose source does not carry them are excluded: " + ", ".join(excluded))
    return "Dotted bars are lower bounds (D-061) — " + "; ".join(parts) + "."


def _bars(ax, series: list[dict[str, str]], colour: str, label: str | None = None) -> None:
    years = [int(r["year"]) for r in series if _count(r["count"]) is not None]
    values = [_count(r["count"]) for r in series if _count(r["count"]) is not None]
    hatches = ["//" if r["partial_year"] == "true" else "" for r in series if _count(r["count"]) is not None]
    bars = ax.bar(years, values, color=colour, label=label, edgecolor="black", linewidth=0.4)
    for bar, hatch in zip(bars, hatches):
        bar.set_hatch(hatch)
    _integer_axis(ax, values)


def _integer_axis(ax, values: list[int | None]) -> None:
    from matplotlib.ticker import MaxNLocator
    top = max([v for v in values if v is not None] + [0])
    ax.set_ylim(0, max(1, top) * 1.15)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))


# ------------------------------------------------------------------ figures
def figure_1(tables: Path, platforms: list[dict[str, str]], cutoff: date, snapshot: str, out: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    rows = _read(tables / "works_by_row_year.csv")
    by_row: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_row[r["row_id"]].append(r)
    plat = {p["row_id"]: p for p in platforms}
    drawn = [rid for rid in by_row if any(_count(r["count"]) is not None for r in by_row[rid])]
    drawn.sort(key=lambda rid: (CLASS_ORDER.index(plat[rid]["initiation_class"]) if plat[rid]["initiation_class"]
                                in CLASS_ORDER else 9, rid))
    n = max(len(drawn), 1)
    cols = 4
    rows_n = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols, figsize=(cols * 3.4, rows_n * 2.4 + 0.8), squeeze=False, sharex=True)
    colours = category_colour_map(CLASS_ORDER)
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, rid in zip(axes.flat, drawn):
        ax.set_visible(True)
        cls = plat[rid]["initiation_class"]
        _bars(ax, by_row[rid], colours.get(cls, "#949494"))
        ax.set_title(f"{plat[rid].get('row_label') or rid}\n({cls})", fontsize=7)
        ax.tick_params(labelsize=6)
    handles = [plt.Rectangle((0, 0), 1, 1, color=colours[c]) for c in CLASS_ORDER]
    fig.legend(handles, CLASS_ORDER, loc="upper right", fontsize=7, title="initiation class", title_fontsize=7)
    fig.suptitle("Figure 1 — Annual evaluated works per register row (row_series; rows without a publishable "
                 "count are omitted)", fontsize=9)
    _footer(fig, cutoff, snapshot)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    return _save(fig, out, "fig1_works_by_row_small_multiples")


def _grouped_bar_figure(path: Path, key: str, order: list[str], title: str, cutoff: date, snapshot: str, out: Path,
                        name: str, small_multiples: bool) -> list[Path]:
    import matplotlib.pyplot as plt
    rows = _read(path)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    cats = [c for c in order if c in groups] + sorted(set(groups) - set(order))
    colours = category_colour_map(cats)
    if small_multiples:
        fig, axes = plt.subplots(1, max(len(cats), 1), figsize=(3.6 * max(len(cats), 1), 3.4), squeeze=False, sharey=True)
        for ax, cat in zip(axes.flat, cats):
            _bars(ax, groups[cat], colours[cat])
            for bar, r in zip(ax.patches, [r for r in groups[cat] if _count(r["count"]) is not None]):
                bar.set_hatch(_hatch(r))
            ax.set_title(cat, fontsize=8)
            ax.tick_params(labelsize=7)
    else:
        fig, ax = plt.subplots(figsize=(9, 4))
        years = sorted({int(r["year"]) for r in rows})
        width = 0.8 / max(len(cats), 1)
        all_values: list[int | None] = []
        for i, cat in enumerate(cats):
            series = {int(r["year"]): r for r in groups[cat]}
            xs, ys, hs = [], [], []
            for y in years:
                r = series.get(y)
                if r is None or _count(r["count"]) is None:
                    continue
                xs.append(y + (i - (len(cats) - 1) / 2) * width)
                ys.append(_count(r["count"]))
                hs.append(_hatch(r))
            bars = ax.bar(xs, ys, width=width, color=colours[cat], label=cat, edgecolor="black", linewidth=0.4)
            for b, h in zip(bars, hs):
                b.set_hatch(h)
            all_values.extend(ys)
        _integer_axis(ax, all_values)
        ax.legend(fontsize=7, title=key, title_fontsize=7)
        ax.tick_params(labelsize=7)
    fig.suptitle(title, fontsize=9)
    bottom = _footer(fig, cutoff, snapshot, " ".join(p for p in ("Deduplicated within each group; groups are not "
                                                                  "summed to a grand total.", _lower_bound_note(rows)) if p))
    fig.tight_layout(rect=(0, bottom + 0.01, 1, 0.94))
    return _save(fig, out, name)


def figure_2(tables, cutoff, snapshot, out):
    return _grouped_bar_figure(tables / "unique_works_by_class_year.csv", "initiation_class", CLASS_ORDER,
                               "Figure 2 — Annual unique works by initiation class (deduplicated within class)",
                               cutoff, snapshot, out, "fig2_unique_works_by_class", small_multiples=False)


def figure_6(tables, cutoff, snapshot, out):
    return _grouped_bar_figure(tables / "unique_works_by_configuration_year.csv", "prc_configuration", CONFIG_ORDER,
                               "Figure 6 — Annual unique works by workflow configuration (deduplicated within "
                               "configuration)", cutoff, snapshot, out, "fig6_unique_works_by_configuration",
                               small_multiples=True)


def figure_3(tables: Path, cutoff: date, snapshot: str, out: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    rows = _read(tables / "unique_works_all_rows_year.csv")
    colours = category_colour_map(CLASS_ORDER)
    fig, ax = plt.subplots(figsize=(9, 4))
    bottoms: dict[int, float] = defaultdict(float)
    for cls in CLASS_ORDER:
        xs, ys, hs = [], [], []
        for r in rows:
            total = _count(r["count"])
            part = _count(r.get(f"n_{cls}_by_earliest_event", ""))
            if not total or part is None:
                continue
            xs.append(int(r["year"]))
            ys.append(part / total)
            hs.append(_hatch(r))
        bars = ax.bar(xs, ys, width=0.8, bottom=[bottoms[x] for x in xs], color=colours[cls], label=cls,
                      edgecolor="black", linewidth=0.4)
        for b, h in zip(bars, hs):
            b.set_hatch(h)
        for x, y in zip(xs, ys):
            bottoms[x] += y
    from matplotlib.ticker import MaxNLocator
    all_years = [int(r["year"]) for r in rows]
    if all_years:
        ax.set_xlim(min(all_years) - 0.6, max(all_years) + 0.6)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylim(0, 1)
    ax.set_ylabel("share of unique works")
    ax.legend(fontsize=7, title="initiation class (earliest counting event)", title_fontsize=7)
    ax.tick_params(labelsize=7)
    fig.suptitle("Figure 3 — Share of initiation classes per year within unique_works_all_rows_year", fontsize=9)
    bottom = _footer(fig, cutoff, snapshot, " ".join(p for p in ("Years with a blank or zero all-row total are not "
                                                                  "drawn. Attribution to a class is relative to the "
                                                                  "rows observable in this run.",
                                                                  _lower_bound_note(rows)) if p))
    fig.tight_layout(rect=(0, bottom + 0.01, 1, 0.94))
    return _save(fig, out, "fig3_class_shares")


def figure_4(tables: Path, cutoff: date, snapshot: str, out: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    rows = _read(tables / "coverage_matrix.csv")
    row_ids = list(dict.fromkeys(r["row_id"] for r in rows))
    years = sorted({int(r["year"]) for r in rows})
    labels = list(COVERAGE_COLOURS)
    index = {lab: i for i, lab in enumerate(labels)}
    lookup = {(r["row_id"], int(r["year"])): r for r in rows}

    def label_of(rid: str, y: int) -> str:
        r = lookup.get((rid, y))
        if r is None:
            return "not_applicable"
        return "register_only" if r["observation_status"] == "register_only" else r["coverage"]

    grid = [[index.get(label_of(rid, y), index["not_applicable"]) for y in years] for rid in row_ids]
    fig, ax = plt.subplots(figsize=(max(6, len(years) * 0.35), max(4, len(row_ids) * 0.28)))
    ax.imshow(grid, aspect="auto", cmap=ListedColormap([COVERAGE_COLOURS[lab] for lab in labels]), vmin=0,
              vmax=len(labels) - 1)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, rotation=90, fontsize=6)
    ax.set_yticks(range(len(row_ids)))
    ax.set_yticklabels(row_ids, fontsize=6)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=COVERAGE_COLOURS[lab], edgecolor="#777777") for lab in labels]
    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=7,
              title="coverage (register_only = no count published)", title_fontsize=7)
    fig.suptitle("Figure 4 — Coverage matrix (row × year); categorical labels, not counts", fontsize=9)
    _footer(fig, cutoff, snapshot, "partial_known_scope marks a yearly lower bound (EGUsphere attribution).")
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    return _save(fig, out, "fig4_coverage_matrix")


def figure_5(tables: Path, cutoff: date, snapshot: str, out: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    rows = _read(tables / "qeios_indicators_by_year.csv")
    indicators = ["new_hosted_works", "hosted_works_with_review", "review_dois", "external_works_reviewed"]
    colours = category_colour_map(indicators)
    fig, ax = plt.subplots(figsize=(9, 4))
    years = [int(r["year"]) for r in rows if any(_count(r[i]) is not None for i in indicators)]
    width = 0.8 / len(indicators)
    all_values: list[int | None] = []
    for i, ind in enumerate(indicators):
        xs, ys, hs = [], [], []
        for r in rows:
            v = _count(r[ind])
            if v is None:
                continue
            xs.append(int(r["year"]) + (i - 1.5) * width)
            ys.append(v)
            hs.append("//" if "year_to_date" in r["year_label"] else "")
        bars = ax.bar(xs, ys, width=width, color=colours[ind], label=ind, edgecolor="black", linewidth=0.4)
        for b, h in zip(bars, hs):
            b.set_hatch(h)
        all_values.extend(ys)
    _integer_axis(ax, all_values)
    if years:
        ax.set_xlim(min(years) - 0.6, max(years) + 0.6)
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=7)
    fig.suptitle("Figure 5 — Qeios indicators by year (deposition diagnostics; two disjoint rows)", fontsize=9)
    _footer(fig, cutoff, snapshot, "Deposit dates after the cutoff are reported in the table, not inferred here.")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    return _save(fig, out, "fig5_qeios_indicators")


def figure_7(tables: Path, cutoff: date, snapshot: str, out: Path) -> list[Path]:
    """Two coordinated categorical panels (§8.9); categories are colours, never numbers."""
    import matplotlib.pyplot as plt
    rows = _read(tables / "evidence_features_by_platform.csv")
    row_ids = [r["row_id"] for r in rows]
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, max(4, len(row_ids) * 0.28)),
                                     gridspec_kw={"width_ratios": [len(RECOGNITION_SIGNALS), 1.2]}, sharey=True)
    for j, sig in enumerate(RECOGNITION_SIGNALS):
        for i, r in enumerate(rows):
            value = (r.get(sig) or "unknown").lower()
            ax_a.add_patch(plt.Rectangle((j, i), 1, 1, color=TRI_STATE_COLOURS.get(value, TRI_STATE_COLOURS["unknown"])))
    ax_a.set_xlim(0, len(RECOGNITION_SIGNALS))
    ax_a.set_ylim(len(rows), 0)
    ax_a.set_xticks([j + 0.5 for j in range(len(RECOGNITION_SIGNALS))])
    ax_a.set_xticklabels(RECOGNITION_SIGNALS, rotation=45, ha="right", fontsize=7)
    ax_a.set_yticks([i + 0.5 for i in range(len(rows))])
    ax_a.set_yticklabels([f"{r['row_id']}  [binding: {r.get('binding_publication_decision') or 'n/a'}]"
                          for r in rows], fontsize=6)
    ax_a.set_title("Panel A — observed signals (true / false / unknown)", fontsize=8)
    ax_a.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in TRI_STATE_COLOURS.values()],
                list(TRI_STATE_COLOURS), loc="upper left", bbox_to_anchor=(0, -0.22), ncol=3, fontsize=7,
                title="Panel A legend", title_fontsize=7)
    for i, r in enumerate(rows):
        value = (r.get("reviewer_identity_disclosed") or "unknown").lower()
        ax_b.add_patch(plt.Rectangle((0, i), 1, 1, color=IDENTITY_COLOURS.get(value, IDENTITY_COLOURS["unknown"])))
    ax_b.set_xlim(0, 1)
    ax_b.set_xticks([0.5])
    ax_b.set_xticklabels(["reviewer_identity_disclosed"], rotation=45, ha="right", fontsize=7)
    ax_b.set_title("Panel B — reviewer identity", fontsize=8)
    ax_b.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in IDENTITY_COLOURS.values()],
                list(IDENTITY_COLOURS), loc="upper left", bbox_to_anchor=(0, -0.22), ncol=2, fontsize=7,
                title="Panel B legend", title_fontsize=7)
    fig.suptitle("Figure 7 — Recognition-signal panels by register row (categorical; binding decision is "
                 "contextual annotation only)", fontsize=9)
    _footer(fig, cutoff, snapshot, "Register evidence fields, not counts.")
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    return _save(fig, out, "fig7_recognition_signals")


# ---------------------------------------------------------------- checksums
def write_checksums(path: Path, roots: Iterable[Path]) -> int:
    lines = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for file in sorted(p for p in root.rglob("*") if p.is_file()):
            if file.resolve() == Path(path).resolve() or file.name == ".gitkeep":
                continue
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            lines.append(f"{digest}  {file.as_posix()}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


# ------------------------------------------------------------------- driver
def run(run_config: RunConfig, sources_config: Mapping[str, Any], platforms: list[Mapping[str, Any]], logger, *,
        processed_root: Path | None = None, tables_root: Path | None = None, figures_root: Path | None = None,
        checksums_path: Path | None = None, **_ignored) -> dict[str, Any]:
    try:
        import matplotlib
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ReportError("matplotlib is required for the report stage: pip install -r requirements.txt") from exc
    matplotlib.use("Agg")
    # D-059 (merged into D-061): stable SVG element ids, so that an SVG re-drawn from
    # unchanged tables is byte-identical (ids only; no geometry change).
    matplotlib.rcParams["svg.hashsalt"] = run_config.run_id
    processed_root = Path(processed_root or DEFAULT_PROCESSED_ROOT)
    tables_root = Path(tables_root or DEFAULT_TABLES_ROOT)
    figures_root = Path(figures_root or DEFAULT_FIGURES_ROOT)
    checksums_path = Path(checksums_path or DEFAULT_CHECKSUMS_PATH)
    cutoff = run_config.analysis_cutoff_date
    snapshot = ""
    manifest_path = processed_root / "analysis_manifest.json"
    if manifest_path.exists():
        import json
        snapshot = str(json.loads(manifest_path.read_text()).get("snapshot_finished_at") or "")
    register = [{k: ("" if v is None else ("; ".join(map(str, v)) if isinstance(v, list) else str(v)))
                 for k, v in row.items() if k != "extraction_selector"} for row in platforms]
    written: list[Path] = []
    written += figure_1(tables_root, register, cutoff, snapshot, figures_root)
    written += figure_2(tables_root, cutoff, snapshot, figures_root)
    written += figure_3(tables_root, cutoff, snapshot, figures_root)
    written += figure_4(tables_root, cutoff, snapshot, figures_root)
    written += figure_5(tables_root, cutoff, snapshot, figures_root)
    written += figure_6(tables_root, cutoff, snapshot, figures_root)
    written += figure_7(tables_root, cutoff, snapshot, figures_root)
    n = write_checksums(checksums_path, [processed_root, tables_root, figures_root])
    logger.event("report_complete", n_figures=len(written), n_checksums=n)
    return {"figures": [str(p) for p in written], "checksums": str(checksums_path), "n_checksums": n}
