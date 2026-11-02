#!/usr/bin/env python3
"""Walk-shape check for a completed run: was any Crossref cursor walk reset mid-way, and is every empty Sciety walk explained by the index?

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
   rule needs the local ``data/raw`` tree (``--raw-root`` or ``$PRC_RAW_STORE``);
6. (Sciety group walks, D-058) a walk that accepted zero items is admissible
   only for a group absent from the unfiltered docmaps index: zero items for
   a group present in the index is an issue, and items for a group absent
   from it is an issue.  The index comes from the run manifest
   (``sciety_index_snapshot``, written by the Sciety stage from its own
   ``index__all`` walk) or from a stored ``/docmaps/v1/index`` response given
   with ``--sciety-index``; with neither, rule 6 is not applied and the
   report says so.  Group identity follows the register (slug URL or group
   id); a count that differs between walk and index is reported as a note.

Rules 1-4 need only ``data/manifests/<run_id>``.  Rule 5 is skipped with
``--no-raw``; pages absent from the raw store make it inconclusive, which is
reported, never passed over.  ``--verify-digests`` additionally compares the
SHA-256 of every stored page with the manifest.

By default only the walk selected in the run manifest is judged for each
scope; ``--all-walks`` judges every complete walk in the folder.  Walks in
other states are listed but never judged (they contribute nothing to counts).

A windowed scope (D-057) appears as one composite walk plus one ordinary
walk per window sub-scope ``<scope>__<field>_<from>_<until>``.  Rules 1-5
apply to each window walk; the composite is judged by its own rules: every
window complete, window totals equal to the unwindowed total before and
after the pass, page count equal to the sum of window pages, and rule 5
across all windows.  The report marks composites with ``composite``.

This script is run locally by the maintainer; it contacts no network service
and changes no file.

Usage::

    python tools/check_walk_shape.py --run run_20261026_01 --no-raw
    python tools/check_walk_shape.py --run run_20261026_01 --raw-root D:/prc/raw
    python tools/check_walk_shape.py --run run_20261026_01 --scope works__10.5194__posted-content --json
    python tools/check_walk_shape.py --run run_20261027_01 --raw-root D:/prc/raw \
        --sciety-index data/manifests/run_20261027_01/evidence/sciety_index_20261028.json

Exit status: 0 when every judged walk is consistent, 1 when at least one
walk has a shape or coverage issue, 2 when the check is inconclusive (missing
run folder, missing raw pages, unreadable manifest or snapshot) and no issue
was found.
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
from src.common.manifest import (DEFAULT_MANIFEST_ROOT, WINDOWED_RULE, ManifestError, WalkRecord,  # noqa: E402
                                 expected_pages, load_run_manifest, read_walk_manifest,
                                 run_manifest_path, verify_walk_against_store,
                                 walk_shape_issues)
from src.common.raw_store import resolve_raw_root, sha256_of_file  # noqa: E402
from src.common.register import load_platforms  # noqa: E402
from src.extract.selectors import ScietyScope, sciety_scopes  # noqa: E402

INCONCLUSIVE_MARKER = "inconclusive"
JUDGED_SOURCES = ("crossref", "sciety")      # OpenAlex walks (D-066) are diagnostic batches: listed, not judged
SCIETY_SOURCE = "sciety"
SCIETY_GROUP_SCOPE_PREFIX = "evaluations__"
SCIETY_NON_GROUP_SCOPES = ("evaluations__full_index",)
SCIETY_GROUP_URL_PREFIX = "https://sciety.org/groups/"


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
    composite: bool = False
    windows: int | None = None
    items_total: int = 0
    index_coverage: str = ""            # rule 6: in_index / not_in_index / "" (not checked)
    index_docmaps: int | None = None
    notes: list[str] = field(default_factory=list)
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


# ---------------------------------------------------------------- rule 6
@dataclass
class ScietyIndex:
    """Docmaps per publisher account in an unfiltered index, plus its provenance."""
    origin: str                          # "run manifest" or the snapshot path
    by_account: dict[str, int]
    docmaps_total: int
    retrieved_at: str = ""
    sha256: str = ""
    scopes: list[ScietyScope] = field(default_factory=list)

    @property
    def has_groups(self) -> bool:
        return any(a.startswith(SCIETY_GROUP_URL_PREFIX) for a in self.by_account)

    def docmaps_for(self, scope_id: str) -> int:
        """Count for one ``evaluations__<slug>`` scope under the register's account matching."""
        matching = [s for s in self.scopes if s.scope_id == scope_id]
        if not matching:
            slug = scope_id[len(SCIETY_GROUP_SCOPE_PREFIX):]
            matching = [ScietyScope(row_id="", group_slug=slug, group_id=None, role="primary")]
        return sum(n for account, n in self.by_account.items()
                   if any(s.account_matches(account) for s in matching))

    def describe(self) -> str:
        parts = [self.origin, f"{self.docmaps_total} docmaps"]
        if self.retrieved_at:
            parts.append(f"retrieved {self.retrieved_at}")
        if self.sha256:
            parts.append(f"sha256 {self.sha256}")
        return ", ".join(parts)


def _register_scopes() -> list[ScietyScope]:
    try:
        return sciety_scopes(load_platforms())
    except Exception:          # the check must still run on a checkout without a readable register
        return []


def load_sciety_index_file(path: Path) -> ScietyIndex:
    """Counts per account from a stored ``/docmaps/v1/index`` response (or a bare docmap list)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    docmaps = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(docmaps, list):
        raise ValueError("snapshot carries no articles array")
    by_account: dict[str, int] = {}
    for docmap in docmaps:
        if not isinstance(docmap, dict):
            continue
        account = str(((docmap.get("publisher") or {}).get("account") or {}).get("id") or "").rstrip("/")
        by_account[account] = by_account.get(account, 0) + 1
    return ScietyIndex(origin=str(path), by_account=by_account, docmaps_total=len(docmaps),
                       sha256=sha256_of_file(path), scopes=_register_scopes())


def sciety_index_from_run_manifest(run_manifest: dict) -> ScietyIndex | None:
    snap = (run_manifest or {}).get("sciety_index_snapshot")
    if not isinstance(snap, dict) or not isinstance(snap.get("groups"), dict):
        return None
    by_account = {str(k).rstrip("/"): int(v) for k, v in snap["groups"].items()}
    digests = snap.get("page_sha256") or []
    return ScietyIndex(origin=f"run manifest sciety_index_snapshot (walk {snap.get('walk_id')})",
                       by_account=by_account, docmaps_total=int(snap.get("docmaps_total") or sum(by_account.values())),
                       retrieved_at=str(snap.get("retrieved_at") or ""),
                       sha256=str(digests[0]) if len(digests) == 1 else "", scopes=_register_scopes())


def is_sciety_group_walk(walk: WalkRecord) -> bool:
    return (walk.source == SCIETY_SOURCE and walk.scope.startswith(SCIETY_GROUP_SCOPE_PREFIX)
            and walk.scope not in SCIETY_NON_GROUP_SCOPES)


def sciety_coverage(walk: WalkRecord, index: ScietyIndex) -> tuple[list[str], list[str], str, int]:
    """``(issues, notes, coverage, docmaps_in_index)`` of one complete Sciety group walk (rule 6)."""
    items = walk.items_total
    n = index.docmaps_for(walk.scope)
    if n == 0:
        if items == 0:
            return [], [], "not_in_index", 0
        return [f"{items} item(s) accepted but the group is absent from the index ({index.origin})"], [], \
            "not_in_index", 0
    if items == 0:
        return [f"group has {n} docmap(s) in the index ({index.origin}) but the walk accepted 0 items"], [], \
            "in_index", n
    notes = [] if items == n else [f"walk accepted {items} item(s), index carries {n} docmap(s)"]
    return [], notes, "in_index", n


# ------------------------------------------------------------- judging
def judge(walk: WalkRecord, rows: int, raw_root: Path | None, selected: bool,
          verify_digests: bool, sciety_index: ScietyIndex | None = None) -> WalkReport:
    report = WalkReport(source=walk.source, scope=walk.scope, walk_id=walk.walk_id, state=walk.state,
                        judged=walk.state == "complete", selected=selected, pages=len(walk.pages),
                        non_empty_pages=sum(1 for p in walk.pages if p.items_in_page > 0),
                        empty_pages=sum(1 for p in walk.pages if p.items_in_page == 0),
                        first_page_total_results=walk.completion.get("first_page_total_results"),
                        total_delta=walk.completion.get("total_delta"),
                        terminal_evidence=walk.completion.get("terminal_evidence", ""),
                        composite=walk.completion.get("rule") == WINDOWED_RULE,
                        items_total=walk.items_total)
    if report.composite:
        report.windows = len(walk.completion.get("windows") or [])
    else:
        report.expected_non_empty_pages = expected_pages(report.first_page_total_results, rows)
    if not report.judged:
        return report
    report.issues = walk_shape_issues(walk, rows, raw_root)
    if verify_digests and raw_root is not None:
        report.digest_problems = verify_walk_against_store(walk, raw_root)
    if sciety_index is not None and is_sciety_group_walk(walk):
        issues, report.notes, report.index_coverage, report.index_docmaps = sciety_coverage(walk, sciety_index)
        report.issues.extend(issues)
    return report


def run_check(run_id: str, manifest_root: Path, raw_root: Path | None, rows: int,
              scopes: list[str] | None, all_walks: bool, verify_digests: bool,
              sciety_index: ScietyIndex | None = None
              ) -> tuple[list[WalkReport], list[str], ScietyIndex | None]:
    """Return ``(reports, errors, index)``; errors are conditions that make the check inconclusive.

    ``index`` is the Sciety index applied under rule 6: the one given, else
    the run manifest's ``sciety_index_snapshot``, else ``None``.
    """
    errors: list[str] = []
    try:
        entries = iter_walks(manifest_root, run_id, scopes)
    except FileNotFoundError as exc:
        return [], [str(exc)], sciety_index
    if not entries:
        errors.append(f"no walk manifests for run {run_id}" + (f" and scopes {scopes}" if scopes else ""))
    run_manifest = load_run_manifest(run_manifest_path(manifest_root, run_id))
    selected = selected_walk_ids(run_manifest)
    if not run_manifest and not all_walks:
        errors.append("no run manifest; every complete walk is judged as if --all-walks were given")
    if sciety_index is None:
        sciety_index = sciety_index_from_run_manifest(run_manifest)
    if sciety_index is not None and not sciety_index.has_groups:
        errors.append(f"sciety index ({sciety_index.origin}) carries no sciety.org group accounts; "
                      "rule 6 would mark every group as absent and is inconclusive")
        sciety_index = None
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
        # Rules 1-6 describe Crossref cursor walks and Sciety index walks; the
        # OpenAlex diagnostic walks (D-066) are batch requests and are listed only.
        judge_this = (walk.state == "complete" and walk.source in JUDGED_SOURCES
                      and (all_walks or not run_manifest or is_selected))
        report = judge(walk, rows, raw_root, is_selected, verify_digests, sciety_index)
        if not judge_this:
            report.judged = False
            report.issues = []
            report.digest_problems = []
            report.notes = []
            report.index_coverage = ""
            report.index_docmaps = None
        reports.append(report)
    return reports, errors, sciety_index


def format_text(reports: list[WalkReport], errors: list[str], run_id: str, rows: int,
                raw_root: Path | None, sciety_index: ScietyIndex | None = None) -> str:
    lines = [f"walk shape check: run {run_id}, rows={rows}, raw store: {raw_root if raw_root else 'not consulted'}",
             f"sciety index (rule 6): {sciety_index.describe() if sciety_index else 'not consulted'}"]
    for r in reports:
        flag = "selected" if r.selected else ""
        head = f"{r.scope:45s} {r.walk_id} {r.state:20s} {flag:8s}"
        if not r.judged:
            lines.append(f"{head} not judged")
            continue
        if r.composite:
            shape = (f"composite windows={r.windows} pages={r.pages} non_empty={r.non_empty_pages} "
                     f"total={r.first_page_total_results} delta={r.total_delta}")
        else:
            shape = (f"pages={r.pages} non_empty={r.non_empty_pages} expected={r.expected_non_empty_pages} "
                     f"empty={r.empty_pages} total={r.first_page_total_results} delta={r.total_delta} "
                     f"terminal={r.terminal_evidence or '-'}")
        if r.source == SCIETY_SOURCE:
            shape += f" items={r.items_total} index={r.index_coverage or 'not checked'}"
            if r.index_docmaps is not None:
                shape += f"({r.index_docmaps})"
        verdict = "ok" if not r.issues and not r.digest_problems else ("INCONCLUSIVE" if r.inconclusive and not r.shape_issues else "ISSUE")
        lines.append(f"{head} {verdict:12s} {shape}")
        for issue in r.issues + r.digest_problems:
            lines.append(f"{'':80s} - {issue}")
        for note in r.notes:
            lines.append(f"{'':80s} - note: {note}")
    judged = [r for r in reports if r.judged]
    with_issues = [r for r in judged if r.shape_issues]
    inconclusive = [r for r in judged if r.inconclusive and not r.shape_issues]
    lines.append(f"judged {len(judged)} complete walk(s): {len(with_issues)} with shape issues, "
                 f"{len(inconclusive)} inconclusive, {len(judged) - len(with_issues) - len(inconclusive)} consistent")
    covered = [r for r in judged if r.index_coverage]
    if covered:
        explained = sum(1 for r in covered if r.index_coverage == "not_in_index" and r.items_total == 0)
        lines.append(f"sciety index coverage: {len(covered)} walk(s) checked, {explained} explained zero(s), "
                     f"{sum(1 for r in covered if r.shape_issues)} with coverage issues")
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
    parser.add_argument("--sciety-index", type=Path, default=None,
                        help="stored /docmaps/v1/index response for rule 6 (default: the run manifest's "
                             "sciety_index_snapshot when present)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    rows = args.rows if args.rows is not None else default_rows()
    if rows <= 0:
        parser.error("--rows must be positive")
    raw_root = None if args.no_raw else resolve_raw_root(args.raw_root)
    if raw_root is not None and not raw_root.is_dir():
        print(f"error: raw root {raw_root} is not a directory (use --no-raw for rules 1-4 only)", file=sys.stderr)
        return 2
    sciety_index: ScietyIndex | None = None
    if args.sciety_index is not None:
        if not args.sciety_index.is_file():
            print(f"error: sciety index snapshot {args.sciety_index} is not a file", file=sys.stderr)
            return 2
        try:
            sciety_index = load_sciety_index_file(args.sciety_index)
        except (OSError, ValueError) as exc:
            print(f"error: sciety index snapshot {args.sciety_index} is unreadable: {exc}", file=sys.stderr)
            return 2
    reports, errors, sciety_index = run_check(args.run_id, args.manifest_root, raw_root, rows, args.scope,
                                              args.all_walks, args.verify_digests, sciety_index)
    status = exit_status(reports, errors)
    if args.json:
        payload = {"run_id": args.run_id, "rows": rows, "raw_root": str(raw_root) if raw_root else None,
                   "exit_status": status, "errors": errors,
                   "sciety_index": ({"origin": sciety_index.origin, "docmaps_total": sciety_index.docmaps_total,
                                     "retrieved_at": sciety_index.retrieved_at, "sha256": sciety_index.sha256,
                                     "groups": dict(sorted(sciety_index.by_account.items()))}
                                    if sciety_index else None),
                   "walks": [dict(asdict(r), inconclusive=r.inconclusive) for r in reports]}
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_text(reports, errors, args.run_id, rows, raw_root, sciety_index))
    return status


if __name__ == "__main__":
    sys.exit(main())
