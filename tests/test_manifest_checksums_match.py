"""Accepted-page manifests must match the bytes of the local raw store.

The raw store lives outside the repository.  Its root is given by the
``PRC_RAW_STORE`` environment variable.  When the variable is unset or the
directory is absent, every check is SKIPPED with an explicit message; the
test never passes silently without verifying bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = REPO_ROOT / "data" / "manifests"
RAW_STORE_ENV = "PRC_RAW_STORE"


def _raw_store() -> Path:
    value = os.environ.get(RAW_STORE_ENV)
    if not value:
        pytest.skip(f"raw store absent: {RAW_STORE_ENV} is not set; checksum verification not performed")
    path = Path(value)
    if not path.is_dir():
        pytest.skip(f"raw store absent: {path} is not a directory; checksum verification not performed")
    return path


def _manifest_files() -> list[Path]:
    return sorted(MANIFEST_DIR.glob("*/*.manifest.jsonl"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_manifest_entries_match_raw_bytes():
    store = _raw_store()
    manifests = _manifest_files()
    if not manifests:
        pytest.skip("no accepted-page manifests present in data/manifests/; nothing to verify")
    mismatches: list[str] = []
    verified = 0
    for manifest in manifests:
        for line_no, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            entry = json.loads(line)
            if "response_path" not in entry or "sha256" not in entry:
                continue
            target = store / entry["response_path"]
            if not target.is_file():
                mismatches.append(f"{manifest.name}:{line_no}: missing {target}")
                continue
            actual = _sha256(target)
            if actual != entry["sha256"]:
                mismatches.append(f"{manifest.name}:{line_no}: sha256 {actual} != {entry['sha256']}")
            verified += 1
    assert not mismatches, "\n".join(mismatches)
    assert verified > 0, "manifests contain no verifiable entries"
