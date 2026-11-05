#!/usr/bin/env python3
"""Insert preset rows into the data-quality log after the last existing preset row.

``data/processed/data_quality_log.csv`` is rewritten by the analysis stage
(D-040): run rows (``origin = run``) follow the preset rows, and the file is
written with the standard library's minimal quoting and LF line ends.  A
unified diff against a hand-kept copy of the file therefore rarely applies.
This script takes the new preset rows as data and places them where the
analysis stage expects them, writing the file with the same writer the stage
uses, so that every untouched line keeps its bytes.

Input forms (``<rows>``):

* a CSV file with the log's header line followed by the rows;
* a CSV file without header, one row per line in the log's column order;
* a unified diff: only lines starting with ``+DQ-`` are read, the leading
  ``+`` is dropped.

Every row is checked before anything is written: twelve columns; ``issue_id``
of the form ``DQ-<three digits>``; ``origin = preset``; ``status`` in
``template`` / ``observed``; empty ``run_id`` and ``walk_id``; ``issue_type``
among the values listed for the column in ``docs/data_dictionary.md``;
``row_id`` present in ``config/platforms.yaml`` or ``all`` (the value the data
dictionary allows for cross-row issues).  A row whose ``issue_id`` is
already in the log is skipped when it is identical and rejected when it
differs, unless ``--replace`` is given.

This script is run locally by the maintainer; it contacts no network service
and the test suite exercises it on a temporary copy of the log.

Usage::

    python tools/append_dq_rows.py new_rows.csv
    python tools/append_dq_rows.py package.diff --dry-run
    python tools/append_dq_rows.py new_rows.csv --log <path> --replace

Exit status: 0 when the rows were inserted (or would be, with ``--dry-run``),
1 when a row failed validation, 2 when the input yields no row.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analyse.build_aggregates import DQ_COLUMNS  # noqa: E402
from src.common.interim import write_csv  # noqa: E402
from src.common.register import load_platforms  # noqa: E402

DEFAULT_LOG = REPO_ROOT / "data" / "processed" / "data_quality_log.csv"
DATA_DICTIONARY = REPO_ROOT / "docs" / "data_dictionary.md"
PLATFORMS = REPO_ROOT / "config" / "platforms.yaml"

PRESET_ID_RE = re.compile(r"^DQ-\d{3}$")
DIFF_ROW_RE = re.compile(r'^\+"?DQ-')
PRESET_STATUSES = {"template", "observed"}


class RowError(ValueError):
    """A new row does not satisfy the preset-row contract."""


# --------------------------------------------------------------------------- inputs
def issue_types(dictionary: Path = DATA_DICTIONARY) -> set[str]:
    """The ``issue_type`` values listed in the data dictionary's column table."""
    for line in dictionary.read_text(encoding="utf-8").splitlines():
        if line.startswith("| `issue_type` | enum |"):
            cell = line.split("|")[3]
            return set(re.findall(r"`([a-z_]+)`", cell))
    raise RowError(f"{dictionary}: no `issue_type` enum line found")


def register_row_ids(platforms: Path = PLATFORMS) -> set[str]:
    """Row identifiers of the validated register."""
    return {str(r["row_id"]) for r in load_platforms(platforms)} | {"all"}


def read_rows(source: Path) -> list[dict[str, str]]:
    """Rows from a CSV (with or without header) or from the ``+DQ-`` lines of a diff."""
    text = source.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    is_diff = any(ln.startswith(("--- ", "+++ ", "@@ ", "diff --git")) for ln in lines)
    if is_diff:
        body = "\n".join(ln[1:] for ln in lines if DIFF_ROW_RE.match(ln))
    else:
        kept = [ln for ln in lines if ln.strip()]
        if kept and kept[0].replace('"', "").strip() == ",".join(DQ_COLUMNS):
            kept = kept[1:]
        body = "\n".join(kept)
    records = [r for r in csv.reader(io.StringIO(body)) if r]
    rows = []
    for n, rec in enumerate(records, 1):
        if len(rec) != len(DQ_COLUMNS):
            raise RowError(f"input row {n}: {len(rec)} columns, {len(DQ_COLUMNS)} expected")
        rows.append(dict(zip(DQ_COLUMNS, rec)))
    return rows


def load_log(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != DQ_COLUMNS:
            raise RowError(f"{path}: header differs from the twelve log columns")
        return [dict(r) for r in reader]


# ----------------------------------------------------------------------- validation
def validate(rows: list[dict[str, str]], types: set[str], row_ids: set[str]) -> None:
    seen: set[str] = set()
    for r in rows:
        iid = r["issue_id"]
        if not PRESET_ID_RE.match(iid):
            raise RowError(f"{iid!r}: preset issue_id must look like DQ-016")
        if iid in seen:
            raise RowError(f"{iid}: listed twice in the input")
        seen.add(iid)
        if r["origin"] != "preset":
            raise RowError(f"{iid}: origin must be 'preset' (got {r['origin']!r})")
        if r["status"] not in PRESET_STATUSES:
            raise RowError(f"{iid}: status must be one of {sorted(PRESET_STATUSES)} (got {r['status']!r})")
        if r["run_id"] or r["walk_id"]:
            raise RowError(f"{iid}: run_id and walk_id must be empty for a preset row")
        if r["issue_type"] not in types:
            raise RowError(f"{iid}: issue_type {r['issue_type']!r} is not in the data dictionary")
        if r["row_id"] not in row_ids:
            raise RowError(f"{iid}: row_id {r['row_id']!r} is neither 'all' nor in config/platforms.yaml")
        if r["n_records_affected"] and not r["n_records_affected"].isdigit():
            raise RowError(f"{iid}: n_records_affected must be an integer or empty")
        for col in ("description", "effect_on_counts", "handling"):
            if not r[col].strip():
                raise RowError(f"{iid}: {col} is empty")


# -------------------------------------------------------------------------- insertion
def merge(existing: list[dict[str, str]], new_rows: list[dict[str, str]], replace: bool = False
          ) -> tuple[list[dict[str, str]], list[str], list[str], list[str]]:
    """Return (rows, inserted_ids, replaced_ids, skipped_ids)."""
    by_id = {r["issue_id"]: r for r in existing}
    inserted, replaced, skipped = [], [], []
    rows = list(existing)
    for r in new_rows:
        iid = r["issue_id"]
        if iid in by_id:
            if by_id[iid] == r:
                skipped.append(iid)
                continue
            if not replace:
                raise RowError(f"{iid}: already in the log with different content (use --replace)")
            idx = next(i for i, x in enumerate(rows) if x["issue_id"] == iid)
            if rows[idx]["origin"] != "preset":
                raise RowError(f"{iid}: the existing row is not a preset row")
            rows[idx] = r
            replaced.append(iid)
            continue
        last_preset = max((i for i, x in enumerate(rows) if x["origin"] == "preset"), default=-1)
        rows.insert(last_preset + 1, r)
        by_id[iid] = r
        inserted.append(iid)
    return rows, inserted, replaced, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rows", type=Path, help="CSV with the new preset rows, or a unified diff with +DQ- lines")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="data-quality log to update")
    parser.add_argument("--replace", action="store_true", help="replace an existing preset row with the same issue_id")
    parser.add_argument("--dry-run", action="store_true", help="validate and report; write nothing")
    args = parser.parse_args(argv)

    try:
        new_rows = read_rows(args.rows)
        if not new_rows:
            print(f"{args.rows}: no DQ row found", file=sys.stderr)
            return 2
        validate(new_rows, issue_types(), register_row_ids())
        existing = load_log(args.log)
        rows, inserted, replaced, skipped = merge(existing, new_rows, replace=args.replace)
    except RowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    position = max((i for i, x in enumerate(rows) if x["origin"] == "preset"), default=-1) + 2  # 1-based, after header
    verb = "would insert" if args.dry_run else "inserted"
    print(f"{verb} {len(inserted)} row(s) {' '.join(inserted)} (last preset row now at line {position}); "
          f"replaced {len(replaced)}; skipped {len(skipped)} identical")
    if not args.dry_run and (inserted or replaced):
        write_csv(args.log, DQ_COLUMNS, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
