"""data/manifests/probes/: every probe file cited in the decision log keeps the bytes recorded in SHA256SUMS."""
from __future__ import annotations

import hashlib
from pathlib import Path

PROBES = Path(__file__).resolve().parents[1] / "data" / "manifests" / "probes"
SUMS = PROBES / "SHA256SUMS"


def _expected() -> dict[str, str]:
    expected = {}
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        expected[name.strip().lstrip("*")] = digest.lower()
    return expected


def test_every_probe_file_is_listed_and_matches() -> None:
    expected = _expected()
    present = sorted(p.name for p in PROBES.iterdir() if p.is_file() and p.name != SUMS.name)
    assert present and present == sorted(expected), "SHA256SUMS and the directory list different files"
    for name, digest in expected.items():
        assert hashlib.sha256((PROBES / name).read_bytes()).hexdigest() == digest, name


def test_cited_sample_digest_is_the_one_in_the_decision_log() -> None:
    """D-065 cites the first and last hex digits of the Review Commons sample file."""
    digest = _expected()["reviewcommons_sample200_2026-10-31.json"].upper()
    assert digest.startswith("7B22A6F4") and digest.endswith("76A7")
