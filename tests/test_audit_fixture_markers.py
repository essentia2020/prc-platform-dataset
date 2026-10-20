"""Fixture markers: mandatory, balanced, and limited to R2/R3."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import audit_text

# Marker strings are assembled at runtime so that this file's own markers
# stay balanced.
BEGIN_PY = "# audit-fixture: " + "begin"
END_PY = "# audit-fixture: " + "end"
BEGIN_MD = "<!-- audit-fixture: " + "begin -->"
END_MD = "<!-- audit-fixture: " + "end -->"

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "audit"


def test_fixture_files_carry_markers():
    files = sorted(p for p in FIXTURE_DIR.iterdir() if p.suffix in (".md", ".py", ".txt"))
    assert files, "no audit fixtures present"
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert audit_text.FIXTURE_BEGIN_RE.search(text), f"{path.name}: missing begin marker"
        assert audit_text.FIXTURE_END_RE.search(text), f"{path.name}: missing end marker"
        audit_text.fixture_spans_of(text)  # balanced


def test_fixture_files_are_clean_under_the_engine(engine):
    for path in sorted(FIXTURE_DIR.iterdir()):
        if path.suffix not in (".md", ".py", ".txt"):
            continue
        rel = path.relative_to(FIXTURE_DIR.parents[2]).as_posix()
        hits = engine.scan(path.read_text(encoding="utf-8"), rel)
        assert hits == [], f"{rel}: " + "; ".join(h.format() for h in hits)


def test_unmarked_fixture_is_reported(engine):
    marked = (FIXTURE_DIR / "version_lineage_fixture.md").read_text(encoding="utf-8")
    unmarked = marked.replace(BEGIN_MD, "").replace(END_MD, "")
    assert engine.scan(marked, "tests/fixtures/audit/version_lineage_fixture.md") == []
    assert engine.scan(unmarked, "tests/fixtures/audit/version_lineage_fixture.md")


def test_unbalanced_markers_are_an_error():
    with pytest.raises(audit_text.AuditConfigError, match="unbalanced"):
        audit_text.fixture_spans_of(BEGIN_PY + "\nx\n")


def test_hash_and_html_marker_forms_are_recognised():
    py = BEGIN_PY + "\nx\n" + END_PY + "\n"
    md = BEGIN_MD + "\nx\n" + END_MD + "\n"
    assert len(audit_text.fixture_spans_of(py)) == 1
    assert len(audit_text.fixture_spans_of(md)) == 1
