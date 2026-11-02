"""reports/CHECKSUMS.txt: every listed file keeps the digest recorded for it,
and every tracked table and figure is listed.

The file covers the processed layer, the tables and the figures (D-005,
D-056). Harvested files of the processed layer are not tracked (D-056) and
may be absent from a clone; they are skipped, never silently passed.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECKSUMS = REPO / "reports" / "CHECKSUMS.txt"
HEX64 = r"[0-9a-fA-F]{64}"
LINE_SUM_FIRST = re.compile(rf"^\s*(?P<digest>{HEX64})\s+\*?(?P<path>\S.*?)\s*$")
LINE_PATH_FIRST = re.compile(rf"^\s*(?P<path>\S.*?)\s+(?P<digest>{HEX64})\s*$")
# D-056: harvested files live in the release archive, not in Git
UNTRACKED = re.compile(r"^data/processed/(records_.*\.csv|works_included\.csv|"
                       r"normalisation_summary\.json|analysis_manifest\.json)$")
MUST_LIST = ("data/processed/data_quality_log.csv",)


def _entries() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_SUM_FIRST.match(line) or LINE_PATH_FIRST.match(line)
        assert m, f"unparsable line in CHECKSUMS.txt: {raw!r}"
        path = m.group("path").replace("\\", "/").lstrip("./")
        assert path not in out, f"{path} listed twice"
        out[path] = m.group("digest").lower()
    assert out, "CHECKSUMS.txt lists no file"
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_required_files_are_listed() -> None:
    entries = _entries()
    for path in MUST_LIST:
        assert path in entries, f"{path} is not listed in CHECKSUMS.txt"


def test_every_tracked_table_and_figure_is_listed() -> None:
    entries = _entries()
    present = sorted(
        p.relative_to(REPO).as_posix()
        for folder in ("reports/tables", "reports/figures")
        for p in (REPO / folder).rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    )
    assert present, "no tables or figures in the working tree"
    missing = [p for p in present if p not in entries]
    assert not missing, f"files present but not listed: {missing}"


def test_listed_digests_match_the_files() -> None:
    entries = _entries()
    checked, skipped, mismatched, absent = 0, [], [], []
    for rel, digest in entries.items():
        path = REPO / rel
        if not path.exists():
            (skipped if UNTRACKED.match(rel) else absent).append(rel)
            continue
        checked += 1
        if _sha256(path) != digest:
            mismatched.append(rel)
    assert not absent, f"listed but missing from the repository: {absent}"
    assert not mismatched, f"digest differs from CHECKSUMS.txt: {mismatched}"
    assert checked, "nothing could be checked"
    if skipped:
        pytest.skip(f"{checked} files match; {len(skipped)} untracked harvested files absent (D-056): {skipped}")