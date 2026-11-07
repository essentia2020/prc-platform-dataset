"""R2 under the release-context rule: stale current-version declarations are
hits even beside deposit anchors; the version of a superseded deposit passes
only through exact file-scoped literals or inside its own versioned
release-notes section; the history scan judges each revision by its own
pyproject version and emits a CONTEXT diagnostic when that context is missing."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import audit_text as a

R15 = frozenset({"1.5.0", "v1.5.0"})
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}


def _engine(allowlist=(), release=R15):
    return a.Engine(tokens=[], allowlist=list(allowlist), current_release=release)


def _r2(engine, text, path="docs/x.md"):
    return [h.matched for h in engine.scan(text, path) if h.rule == "R2"]


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=GIT_ENV)


# audit-fixture: begin
STALE_NEAR_ANCHOR = "PRC Platform Dataset 1.4.0 is the current release (archive deposited as 10.5281/zenodo.23891928)."
STALE_DECISIONS = "- **Decision:** release 1.4.0 is the current dataset.\n"
STALE_NOTES = "## 1.5.0\n\nThis release 1.4.0 of the dataset is current.\n"
HISTORICAL = "The 1.4.0 archive of this dataset was deposited on 2026-11-02 (10.5281/zenodo.23891928)."
HISTORICAL_LITERAL = "The 1.4.0 archive of this dataset was deposited on 2026-11-02"
NOTES = ("## 1.5.0\n\nCurrent release of the dataset.\n\n## 1.4.0\n\nRelease 1.4.0 of the dataset, "
         "deposited 2026-11-02; see the previous release notes.\n\n### Notes\n\nStill the 1.4.0 release "
         "section, v1.4.0 form. Not 1.4.0.1 either.\n\n## Appendix\n\nRelease 1.4.0 mentioned after the section.\n")
STALE_LINE = "PRC Platform Dataset 1.4.0 is the current release.\n"
LINEAGE_WORD = "previous release"
# audit-fixture: end


def test_stale_declaration_beside_deposit_anchor_is_a_hit():
    assert _r2(_engine(), STALE_NEAR_ANCHOR) == ["1.4.0"]


def test_stale_text_in_decisions_and_release_notes_is_a_hit():
    assert _r2(_engine(), STALE_DECISIONS, "docs/decisions.md") == ["1.4.0"]
    assert _r2(_engine(), STALE_NOTES, "docs/release_notes.md") == ["1.4.0"]


def test_historical_reference_passes_only_through_its_exact_file_scoped_literal():
    assert _r2(_engine(), HISTORICAL, "docs/decisions.md") == ["1.4.0"]
    allow = [a.AllowEntry("R2", "docs/decisions.md", literal=HISTORICAL_LITERAL)]
    assert _r2(_engine(allow), HISTORICAL, "docs/decisions.md") == []
    assert _r2(_engine(allow), HISTORICAL, "docs/limitations.md") == ["1.4.0"]
    assert _r2(_engine(allow), STALE_DECISIONS, "docs/decisions.md") == ["1.4.0"]


def test_release_notes_historical_section_is_bounded_and_version_specific():
    hits = [h.matched for h in _engine().scan(NOTES, "docs/release_notes.md") if h.rule == "R2"]
    assert hits.count("1.4.0") == 2            # "1.4.0" inside "1.4.0.1", and the mention after "## Appendix"
    assert "v1.4.0" in hits                     # the v-form inside the section is not exempt
    assert LINEAGE_WORD in hits           # a lineage word inside the section is not exempt
    assert _r2(_engine(), NOTES, "docs/other.md").count("1.4.0") == 5   # heading, two body mentions, 1.4.0.1, appendix


def test_extended_tokens_inside_historical_section_are_reported():
    # audit-fixture: begin
    text = "## 1.4.0\n\nThis release section of the dataset mentions 1.4.0.1 and 1.4.0-beta.\n"
    # audit-fixture: end
    assert _r2(_engine(), text, "docs/release_notes.md") == ["1.4.0", "1.4.0"]


def test_current_release_constant_matches_pyproject_and_parser_is_strict():
    root = Path(__file__).resolve().parents[1]
    assert a.release_from_pyproject((root / "pyproject.toml").read_text(encoding="utf-8")) == frozenset(a.CURRENT_RELEASE)
    with pytest.raises(a.AuditConfigError):
        a.release_from_pyproject('[build-system]\nversion = "9.9.9"\n')
    with pytest.raises(a.AuditConfigError):
        a.release_from_pyproject(None)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_identical_blob_is_judged_per_revision(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text(STALE_LINE, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.4.0"\n', encoding="utf-8")
    _git(tmp_path, "add", "."); _git(tmp_path, "commit", "-q", "-m", "r1")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.5.0"\n', encoding="utf-8")
    _git(tmp_path, "add", "."); _git(tmp_path, "commit", "-q", "-m", "r2")
    hits = a.audit_history(_engine(), tmp_path)
    revs = subprocess.run(["git", "rev-list", "--all"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.split()
    assert [h.revision for h in hits if h.rule == "R2" and h.path == "docs/x.md"] == [revs[0]]
    assert not [h for h in hits if h.rule == "CONTEXT"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_missing_release_context_is_an_explicit_diagnostic(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text(STALE_LINE, encoding="utf-8")
    _git(tmp_path, "add", "."); _git(tmp_path, "commit", "-q", "-m", "no pyproject")
    hits = a.audit_history(_engine(), tmp_path)
    assert [h.rule for h in hits if h.path == "pyproject.toml"] == ["CONTEXT"]
    assert [h.matched for h in hits if h.rule == "R2" and h.path == "docs/x.md"] == ["1.4.0"]

# --- structural allow-list exemption (approved 2026-11-06) ------------------
# audit-fixture: begin
D006 = "- **Question:** Will release 1.4.0 use a new Zenodo concept record or"
STRUCTURAL_YAML = (
    "allowlist:\n"
    "  - rule_id: R2\n    file: docs/decisions.md\n"
    f'    literal: "{D006}"\n'
    "  - rule_id: R2\n    file: config/audit_allowlist.yaml\n    yaml_path: allowlist[*].literal\n"
)
STRUCTURAL_WITH_COMMENT = STRUCTURAL_YAML + "  # note: release 1.4.0 is the current dataset\n"
STRUCTURAL_WITH_SIBLING = STRUCTURAL_YAML.replace(
    "    yaml_path:", "    note: release 1.4.0 is the current dataset\n    yaml_path:")
ISOLATION_SUFFIX = " hunter2 Corker"
OLD = "1.4.0"
CITE = "Corker"
# audit-fixture: end
ALLOWLIST_FILE = "config/audit_allowlist.yaml"


def _structural_engine(text=STRUCTURAL_YAML, tokens=()):
    return a.Engine(tokens=list(tokens), allowlist=a.parse_allowlist(text), current_release=R15)


def test_structural_entry_exempts_only_selected_literal_values_in_the_exact_file():
    assert _r2(_structural_engine(), STRUCTURAL_YAML, ALLOWLIST_FILE) == []
    assert _r2(_structural_engine(STRUCTURAL_WITH_COMMENT), STRUCTURAL_WITH_COMMENT, ALLOWLIST_FILE) == [OLD]
    assert _r2(_structural_engine(STRUCTURAL_WITH_SIBLING), STRUCTURAL_WITH_SIBLING, ALLOWLIST_FILE) == [OLD]
    assert _r2(_structural_engine(), STRUCTURAL_YAML, "config/other_allowlist.yaml") == [OLD]
    assert _r2(_structural_engine(), D006 + " of the dataset", "docs/other.md") == [OLD]


def test_structural_entry_leaves_r1_r3_r4_unchanged():
    token = ("hunter2", re.compile("hunter2"))
    text = STRUCTURAL_YAML.replace("concept record", "concept record" + ISOLATION_SUFFIX)
    with_entry = _structural_engine(text, [token]).scan(text, ALLOWLIST_FILE)
    without_entry = a.Engine(tokens=[token], allowlist=a.parse_allowlist(text)[:1], current_release=R15).scan(text, ALLOWLIST_FILE)
    other = lambda hits: sorted((h.rule, h.matched) for h in hits if h.rule != "R2")
    assert ("R1", "hunter2") in other(with_entry)
    assert ("R3", CITE) in other(with_entry)
    assert other(with_entry) == other(without_entry)
    assert [h.matched for h in with_entry if h.rule == "R2"] == []
    assert [h.matched for h in without_entry if h.rule == "R2"] == [OLD]


def test_declaration_tests_do_not_depend_on_the_audit_engine_or_allow_list():
    src = Path(__file__).with_name("test_release_declarations.py").read_text(encoding="utf-8")
    assert "audit_text" not in src and "allowlist" not in src and "audit-fixture" not in src
