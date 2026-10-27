#!/usr/bin/env python3
"""Walk-shape check for a completed run: was any Crossref cursor walk reset mid-way?

``total_delta == 0`` in a walk manifest is a necessary condition for a clean
walk, not a proof: a reset re-serves pages, and deposits landing during the
walk can move total-results by exactly the re-served amount.  The proof is
the page sequence.  For every complete walk of the run this script applies
``src.common.manifest.walk_shape_issues``:

1. no ``cursor_in`` value occurs twice (a repeated cursor is a reset or a loop);
2. the number of non-empty pages equals ``ceil(first_page_total_results / rows)``;
3. at most one empty page, and only as the terminal page;
4. no short page before the last non-empty page;
5. no record (DOI) accepted on two pages — read from the raw store, so this
   rule needs the local ``data/raw`` tree (``--raw-root`` or ``$PRC_RAW_STORE``).

Rules 1-4 need only ``data/manifests/<run_id>``.  Rule 5 is skipped with
``--no-raw``; pages absent from the raw store make it inconclusive, which is
reported, never passed over.  ``--verify-digests`` additionally compares the
SHA-256 of every stored page with the manifest.

By default only the walk selected in the run manifest is judged for each
scope; ``--all-walks`` judges every complete walk in the folder.  Walks in
other states are listed but never judged (they contribute nothing to counts).

This script is run locally by the maintainer; it contacts no network service
and changes no file.

Usage::

    python tools/check_walk_shape.py --run run_20261026_01 --no-raw
    python tools/check_walk_shape.py --run run_20261026_01 --raw-root D:/prc/raw
    python tools/check_walk_shape.py --run run_20261026_01 --scope works__10.5194__posted-content --json

Exit status: 0 when every judged walk is consistent, 1 when at least one
walk has a shape issue, 2 when the check is inconclusive (missing run folder,
missing raw pages, unreadable manifest) and no shape issue was found.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_sources_config  # noqa: E402
from src.common.manifest import (DEFAULT_MANIFEST_ROOT, ManifestError, WalkRecord,  # noqa: E402
                                 expected_pages, load_run_manifest, read_walk_manifest,
                                 run_manifest_path, verify_walk_against_store,
                                 walk_shape_issues)
from src.common.raw_store import resolve_raw_root  # noqa: E402

INCONCLUSIVE_MARKER = "inconclusive"


@dataclass
class WalkReport:
    source: str
    scope: str
    walk_id: str
    state: str
    judged: bool
    selected: bool
    pages: int = 0
    non_empty_pages: int = 0
    empty_pages: int = 0
    expected_non_empty_pages: int | None = None
    first_page_total_results: int | None = None
    total_delta: int | None = None
    terminal_evidence: str = ""
    issues: list[str] = field(default_factory=list)
    digest_problems: list[str] = field(default_factory=list)

    @property
    def inconclusive(self) -> bool:
        return any(INCONCLUSIVE_MARKER in i for i in self.issues)

    @property
    def shape_issues(self) -> list[str]:
        return [i for i in self.issues if INCONCLUSIVE_MARKER not in i] + self.digest_problems


def _parse_walk_filename(path: Path) -> tuple[str, str, str] | None:
    stem = path.name[: -len(".manifest.jsonl")]
    parts = stem.split("__")
    if len(parts) < 3:
        return None
    return parts[0], "__".join(parts[1:-1]), parts[-1]


def iter_walks(manifest_root: Path, run_id: str, scopes: Iterable[str] | None) -> list[tuple[Path, str, str, str]]:
    folder = manifest_root / run_id
    if not folder.is_dir():
        raise FileNotFoundError(f"no manifest folder {folder}")
    wanted = set(scopes or [])
    found = []
    for path in sorted(folder.glob("*.manifest.jsonl")):
        parsed = _parse_walk_filename(path)
        if parsed is None:
            continue
        source, scope, walk_id = parsed
        if wanted and scope not in wanted:
            continue
        found.append((path, source, scope, walk_id))
    return found


def selected_walk_ids(run_manifest: dict) -> dict[str, str]:
    out = {}
    for key, entry in (run_manifest.get("scopes") or {}).items():
        walk_id = entry.get("selected_walk_id")
        if walk_id:
            out[key] = walk_id
    return out


def judge(walk: WalkRecord, rows: int, raw_root: Path | None, selected: bool,
          verify_digests: bool) -> WalkReport:
    report = WalkReport(source=walk.source, scope=walk.scope, walk_id=walk.walk_id, state=walk.state,
                        judged=walk.state == "complete", selected=selected, pages=len(walk.pages),
                        non_empty_pages=sum(1 for p in walk.pages if p.items_in_page > 0),
                        empty_pages=sum(1 for p in walk.pages if p.items_in_page == 0),
                        first_page_total_results=walk.completion.get("first_page_total_results"),
                        total_delta=walk.completion.get("total_delta"),
                        terminal_evidence=walk.completion.get("terminal_evidence", ""))
    report.expected_non_empty_pages = expected_pages(report.first_page_total_results, rows)
    if not report.judged:
        return report
    report.issues = walk_shape_issues(walk, rows, raw_root)
    if verify_digests and raw_root is not None:
        report.digest_problems = verify_walk_against_store(walk, raw_root)
    return report


def run_check(run_id: str, manifest_root: Path, raw_root: Path | None, rows: int,
              scopes: list[str] | None, all_walks: bool, verify_digests: bool) -> tuple[list[WalkReport], list[str]]:
    """Return ``(reports, errors)``; errors are conditions that make the check inconclusive."""
    errors: list[str] = []
    try:
        entries = iter_walks(manifest_root, run_id, scopes)
    except FileNotFoundError as exc:
        return [], [str(exc)]
    if not entries:
        errors.append(f"no walk manifests for run {run_id}" + (f" and scopes {scopes}" if scopes else ""))
    run_manifest = load_run_manifest(run_manifest_path(manifest_root, run_id))
    selected = selected_walk_ids(run_manifest)
    if not run_manifest and not all_walks:
        errors.append("no run manifest; every complete walk is judged as if --all-walks were given")
    reports: list[WalkReport] = []
    for path, source, scope, walk_id in entries:
        key = f"{source}/{scope}"
        is_selected = selected.get(key) == walk_id
        try:
            walk = read_walk_manifest(path)
        except ManifestError as exc:
            errors.append(str(exc))
            reports.append(WalkReport(source, scope, walk_id, "unreadable", judged=False, selected=is_selected))
            continue
        judge_this = walk.state == "complete" and (all_walks or not run_manifest or is_selected)
        report = judge(walk, rows, raw_root, is_selected, verify_digests)
        if not judge_this:
            report.judged = False
            report.issues = []
            report.digest_problems = []
        reports.append(report)
    return reports, errors


def format_text(reports: list[WalkReport], errors: list[str], run_id: str, rows: int,
                raw_root: Path | None) -> str:
    lines = [f"walk shape check: run {run_id}, rows={rows}, raw store: {raw_root if raw_root else 'not consulted'}"]
    for r in reports:
        flag = "selected" if r.selected else ""
        head = f"{r.scope:45s} {r.walk_id} {r.state:20s} {flag:8s}"
        if not r.judged:
            lines.append(f"{head} not judged")
            continue
        shape = (f"pages={r.pages} non_empty={r.non_empty_pages} expected={r.expected_non_empty_pages} "
                 f"empty={r.empty_pages} total={r.first_page_total_results} delta={r.total_delta} "
                 f"terminal={r.terminal_evidence or '-'}")
        verdict = "ok" if not r.issues and not r.digest_problems else ("INCONCLUSIVE" if r.inconclusive and not r.shape_issues else "ISSUE")
        lines.append(f"{head} {verdict:12s} {shape}")
        for issue in r.issues + r.digest_problems:
            lines.append(f"{'':80s} - {issue}")
    judged = [r for r in reports if r.judged]
    with_issues = [r for r in judged if r.shape_issues]
    inconclusive = [r for r in judged if r.inconclusive and not r.shape_issues]
    lines.append(f"judged {len(judged)} complete walk(s): {len(with_issues)} with shape issues, "
                 f"{len(inconclusive)} inconclusive, {len(judged) - len(with_issues) - len(inconclusive)} consistent")
    for err in errors:
        lines.append(f"error: {err}")
    return "\n".join(lines)


def exit_status(reports: list[WalkReport], errors: list[str]) -> int:
    judged = [r for r in reports if r.judged]
    if any(r.shape_issues for r in judged):
        return 1
    if errors or any(r.inconclusive for r in judged):
        return 2
    return 0


def default_rows() -> int:
    pagination = load_sources_config()["sources"]["crossref"]["pagination"]
    return int(pagination["rows"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, dest="run_id", help="run id, e.g. run_20261026_01")
    parser.add_argument("--manifest-root", type=Path, default=DEFAULT_MANIFEST_ROOT,
                        help="manifest root (default data/manifests)")
    parser.add_argument("--raw-root", type=Path, default=None,
                        help="raw store root for rule 5 (default $PRC_RAW_STORE, else data/raw)")
    parser.add_argument("--no-raw", action="store_true", help="skip rule 5 (manifest-only check)")
    parser.add_argument("--rows", type=int, default=None,
                        help="page size used by the walks (default: sources.yaml pagination.rows)")
    parser.add_argument("--scope", action="append", default=None, help="restrict to a scope id (repeatable)")
    parser.add_argument("--all-walks", action="store_true",
                        help="judge every complete walk, not only the one selected in the run manifest")
    parser.add_argument("--verify-digests", action="store_true",
                        help="also compare the SHA-256 of every stored page with the manifest")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    rows = args.rows if args.rows is not None else default_rows()
    if rows <= 0:
        parser.error("--rows must be positive")
    raw_root = None if args.no_raw else resolve_raw_root(args.raw_root)
    if raw_root is not None and not raw_root.is_dir():
        print(f"error: raw root {raw_root} is not a directory (use --no-raw for rules 1-4 only)", file=sys.stderr)
        return 2
    reports, errors = run_check(args.run_id, args.manifest_root, raw_root, rows, args.scope,
                                args.all_walks, args.verify_digests)
    status = exit_status(reports, errors)
    if args.json:
        payload = {"run_id": args.run_id, "rows": rows, "raw_root": str(raw_root) if raw_root else None,
                   "exit_status": status, "errors": errors,
                   "walks": [dict(asdict(r), inconclusive=r.inconclusive) for r in reports]}
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_text(reports, errors, args.run_id, rows, raw_root))
    return status


if __name__ == "__main__":
    sys.exit(main())
