"""Exact scope of the structural allow-list entry, failure handling of the
revision context, TOML parsing of the release version, and cache behaviour."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from tools import audit_text as a

R15 = frozenset({"1.5.0", "v1.5.0"})
ALLOW = "config/audit_allowlist.yaml"
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")

# audit-fixture: begin
D006 = "- **Question:** Will release 1.4.0 use a new Zenodo concept record or"
BASE = ("allowlist:\n  - rule_id: R2\n    file: docs/decisions.md\n"
        f'    literal: "{D006}"\n'
        "  - rule_id: R2\n    file: config/audit_allowlist.yaml\n    yaml_path: allowlist[*].literal\n")
SAME_IN_COMMENT = BASE + f"# {D006}\n"
SAME_IN_SIBLING = BASE.replace("    yaml_path:", f'    note: "{D006}"\n    yaml_path:')
BLOCK_SCALAR = ("allowlist:\n  - rule_id: R2\n    file: docs/decisions.md\n    literal: |\n"
                "      release 1.4.0 line one\n      release 1.4.0 line two\n"
                "  - rule_id: R2\n    file: config/audit_allowlist.yaml\n    yaml_path: allowlist[*].literal\n"
                "# release 1.4.0 line one\n")
STALE_OLD = "PRC Platform Dataset 1.4.0 is the current release.\n"
STALE_CUR = "PRC Platform Dataset 1.5.0 is the current release.\n"
OLD, CUR = "1.4.0", "1.5.0"
PYPROJECT_15 = '[project]\nname = "x"\nversion = "1.5.0"\n'
PYPROJECT_BROKEN = '[project]\nversion = "1.5.0"\nbroken = [\n'
ALLOW_EXEMPTING_OLD = f'allowlist:\n  - rule_id: R2\n    file: docs/x.md\n    literal: "{STALE_OLD.strip()}"\n'
VALID_TOML = [
    '[project]\nname = "x"\nversion = "1.5.0"\n',
    "[project]\nname = 'x'\nversion = '1.5.0'\n",
    '[project]\nauthors = [{name = "A"}]\nversion = "1.5.0"\n',
    '[build-system]\nrequires = []\n\n[project]\nversion = "1.5.0"\n',
]
INVALID_CONTEXT = [PYPROJECT_BROKEN, '[build-system]\nversion = "9.9.9"\n', '[project]\nname = "x"\n',
                   "[project]\nversion = 150\n", None]
BAD_ALLOWLISTS = ["allowlist: [\n", "- not a mapping\n", b"\x00\x01binary\x00",
                  "allowlist:\n  - rule_id: R9\n    file: x\n    literal: y\n"]
# audit-fixture: end


def _r2(engine, text, path):
    return [h.matched for h in engine.scan(text, path) if h.rule == "R2"]


def _engine(text):
    return a.Engine(tokens=[], allowlist=a.parse_allowlist(text), current_release=R15)


def test_structural_entry_covers_selected_scalar_nodes_only():
    assert _r2(_engine(BASE), BASE, ALLOW) == []
    assert _r2(_engine(SAME_IN_COMMENT), SAME_IN_COMMENT, ALLOW) == [OLD]
    assert _r2(_engine(SAME_IN_SIBLING), SAME_IN_SIBLING, ALLOW) == [OLD]
    assert _r2(_engine(BASE), BASE, "config/other.yaml") == [OLD]


def test_block_scalar_is_covered_but_its_fragments_do_not_leak():
    assert _r2(_engine(BLOCK_SCALAR), BLOCK_SCALAR, ALLOW) == [OLD]


def test_yaml_path_source_spans_select_nodes_and_reject_bad_yaml():
    spans = a.yaml_path_source_spans(BASE, "allowlist[*].literal")
    assert [BASE[s.start:s.end] for s in spans] == [f'"{D006}"']
    with pytest.raises(a.AuditConfigError):
        a.yaml_path_source_spans("allowlist: [", "allowlist[*].literal")


def test_parse_allowlist_normalises_failures_and_accepts_empty_policy():
    with pytest.raises(a.AuditConfigError):
        a.parse_allowlist("allowlist: [")
    with pytest.raises(a.AuditConfigError):
        a.parse_allowlist("- not a mapping\n")
    assert a.parse_allowlist("") == []
    assert a.parse_allowlist("allowlist: []\n") == []


@pytest.mark.parametrize("text", VALID_TOML)
def test_release_from_pyproject_parses_valid_toml(text):
    assert a.release_from_pyproject(text) == R15


@pytest.mark.parametrize("text", INVALID_CONTEXT)
def test_release_from_pyproject_rejects_invalid_context(text):
    with pytest.raises(a.AuditConfigError):
        a.release_from_pyproject(text)


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=GIT_ENV)


def _committer(root):
    _git(root, "init", "-q")
    def commit(files, msg):
        for rel, data in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", msg)
    return commit


def _history(root):
    hits = a.audit_history(a.Engine(tokens=[], allowlist=[], current_release=R15), root)
    revs = subprocess.run(["git", "rev-list", "--all"], cwd=root, check=True, capture_output=True, text=True).stdout.split()
    return hits, revs


@needs_git
@pytest.mark.parametrize("bad", BAD_ALLOWLISTS)
def test_unreadable_allowlist_is_a_context_diagnostic_and_strict(tmp_path, bad):
    _committer(tmp_path)({"docs/x.md": STALE_CUR, "pyproject.toml": PYPROJECT_15, ALLOW: bad}, "r1")
    hits, _ = _history(tmp_path)
    assert [h.path for h in hits if h.rule == "CONTEXT"] == [ALLOW]
    assert [h.matched for h in hits if h.rule == "R2" and h.path == "docs/x.md"] == [CUR]


@needs_git
def test_malformed_pyproject_is_a_context_diagnostic_and_strict(tmp_path):
    _committer(tmp_path)({"docs/x.md": STALE_CUR, "pyproject.toml": PYPROJECT_BROKEN}, "r1")
    hits, _ = _history(tmp_path)
    assert [h.path for h in hits if h.rule == "CONTEXT"] == ["pyproject.toml"]
    assert [h.matched for h in hits if h.rule == "R2" and h.path == "docs/x.md"] == [CUR]


@needs_git
def test_readable_empty_allowlist_is_not_a_diagnostic(tmp_path):
    _committer(tmp_path)({"docs/x.md": STALE_CUR, "pyproject.toml": PYPROJECT_15, ALLOW: "allowlist: []\n"}, "r1")
    hits, _ = _history(tmp_path)
    assert not [h for h in hits if h.rule == "CONTEXT"]
    assert not [h for h in hits if h.rule == "R2" and h.path == "docs/x.md"]


@needs_git
def test_unchanged_blob_is_rejudged_when_only_the_allowlist_changes(tmp_path):
    commit = _committer(tmp_path)
    commit({"docs/x.md": STALE_OLD, "pyproject.toml": PYPROJECT_15, ALLOW: ALLOW_EXEMPTING_OLD}, "r1")
    commit({ALLOW: "allowlist: []\n"}, "r2")
    hits, revs = _history(tmp_path)
    assert [h.revision for h in hits if h.rule == "R2" and h.path == "docs/x.md"] == [revs[0]]
    assert not [h for h in hits if h.rule == "CONTEXT"]


@needs_git
def test_repeated_invalid_context_is_diagnosed_per_revision(tmp_path):
    commit = _committer(tmp_path)
    commit({"docs/x.md": STALE_CUR, "pyproject.toml": PYPROJECT_15, ALLOW: "allowlist: [\n"}, "r1")
    commit({"docs/y.md": "nothing here\n"}, "r2")
    hits, revs = _history(tmp_path)
    assert sorted(h.revision for h in hits if h.rule == "CONTEXT") == sorted(revs)
    assert [h.matched for h in hits if h.rule == "R2" and h.path == "docs/x.md"] == [CUR]