"""Boundary regressions for the S2 structural-exemption and strict-context safeguards."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

try:
    from tools import audit_text as at
except ImportError:  # pragma: no cover
    import audit_text as at  # type: ignore[no-redef]

CURRENT = frozenset({"1.5.0", "v1.5.0"})
PYPROJECT = b'[project]\nname = "x"\nversion = "1.5.0"\n'
NOTES = b"## 1.5.0\n\nPRC Platform Dataset 1.5.0 is the current release.\n"

# audit-fixture: begin
ALIAS_YAML = (
    'note: &outside "- **Question:** Will release 1.4.0 use a new Zenodo concept record or"\n'
    "allowlist:\n"
    "  - rule_id: R2\n"
    "    file: docs/decisions.md\n"
    "    literal: *outside\n"
    "  - rule_id: R2\n"
    "    file: config/audit_allowlist.yaml\n"
    "    yaml_path: allowlist[*].literal\n"
)
PLAIN_YAML = (
    "allowlist:\n"
    "  - rule_id: R2\n"
    "    file: docs/decisions.md\n"
    '    literal: "Will release 1.4.0 use a new Zenodo concept record"\n'
    "  - rule_id: R2\n"
    "    file: config/audit_allowlist.yaml\n"
    "    yaml_path: allowlist[*].literal\n"
)
# audit-fixture: end


def _repo(tmp_path: Path, files: dict[str, bytes]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}
    for args in (["init", "-q"], ["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, env=env, capture_output=True)
    return root


def _history(files: dict[str, bytes], tmp_path: Path) -> list:
    return at.audit_history(at.Engine(tokens=[]), _repo(tmp_path, files))


def _context(hits: list, path: str) -> list:
    return [h for h in hits if h.rule == "CONTEXT" and h.path == path]


def _declaration(hits: list) -> list:
    return [h for h in hits if h.rule == "R2" and h.path == at.RELEASE_NOTES_PATH and h.line == 3 and h.matched == "1.5.0"]


# -- YAML alias leakage -------------------------------------------------------

def test_alias_to_anchor_outside_selected_path_yields_no_span():
    assert at.yaml_path_source_spans(ALIAS_YAML, "allowlist[*].literal") == []


def test_alias_cannot_exempt_anchor_in_unrelated_field():
    engine = at.Engine(tokens=[], allowlist=at.parse_allowlist(ALIAS_YAML), current_release=CURRENT)
    hits = [h for h in engine.scan(ALIAS_YAML, "config/audit_allowlist.yaml") if h.rule == "R2"]
    assert [(h.line, h.matched) for h in hits] == [(1, "1.4.0")]


def test_plain_scalar_on_selected_path_is_still_exempt():
    spans = at.yaml_path_source_spans(PLAIN_YAML, "allowlist[*].literal")
    assert len(spans) == 1
    engine = at.Engine(tokens=[], allowlist=at.parse_allowlist(PLAIN_YAML), current_release=CURRENT)
    assert [h for h in engine.scan(PLAIN_YAML, "config/audit_allowlist.yaml") if h.rule == "R2"] == []


# -- invalid metadata ---------------------------------------------------------

@pytest.mark.parametrize("data", [b"# malformed byte: \xff\nallowlist: []\n", b"a\0b"])
def test_read_metadata_text_rejects_undecodable_bytes(data):
    with pytest.raises(at.AuditConfigError):
        at.read_metadata_text(data, "x")


def test_read_metadata_text_normalises_newlines():
    assert at.read_metadata_text(b"a\r\nb\rc\n", "x") == "a\nb\nc\n"


@pytest.mark.parametrize("text", ["", "null\n", "# only a comment\n", "allowlist: []\n"])
def test_parse_allowlist_accepts_valid_empty_policies(text):
    assert at.parse_allowlist(text) == []


@pytest.mark.parametrize("text", ["false\n", "0\n", "[]\n", '"text"\n', "- a\n"])
def test_parse_allowlist_rejects_non_mapping_roots(text):
    with pytest.raises(at.AuditConfigError, match="root must be a mapping"):
        at.parse_allowlist(text)


@pytest.mark.parametrize("allow_bytes", [
    b"# malformed byte: \xff\nallowlist: []\n",
    b"allowlist: []\0",
    b"false\n",
    b"0\n",
    b"[]\n",
    b'"text"\n',
    b"allowlist: [\n",
])
def test_history_invalid_allowlist_emits_context_and_judges_strictly(tmp_path, allow_bytes):
    hits = _history({"pyproject.toml": PYPROJECT, "config/audit_allowlist.yaml": allow_bytes,
                     at.RELEASE_NOTES_PATH: NOTES}, tmp_path)
    assert _context(hits, "config/audit_allowlist.yaml")
    assert _declaration(hits)


@pytest.mark.parametrize("pyproject_bytes", [
    b'[project]\nname = "x"\nversion = "1.5.0"\n# \xff\n',
    b'[project]\nname = "x"\nversion = "1.5.0"\n\0',
])
def test_history_invalid_pyproject_emits_context_and_judges_strictly(tmp_path, pyproject_bytes):
    hits = _history({"pyproject.toml": pyproject_bytes, "config/audit_allowlist.yaml": b"allowlist: []\n",
                     at.RELEASE_NOTES_PATH: NOTES}, tmp_path)
    assert _context(hits, "pyproject.toml")
    assert _declaration(hits)


@pytest.mark.parametrize("allow_bytes", [b"", b"null\n", b"allowlist: []\n"])
def test_history_valid_empty_policy_has_no_context_and_no_hits(tmp_path, allow_bytes):
    hits = _history({"pyproject.toml": PYPROJECT, "config/audit_allowlist.yaml": allow_bytes,
                     at.RELEASE_NOTES_PATH: NOTES}, tmp_path)
    assert [h for h in hits if h.rule == "CONTEXT"] == []
    assert [h for h in hits if h.rule == "R2"] == []


# -- strict fallback and section exemption -----------------------------------

def test_strict_engine_disables_release_notes_section_exemption():
    strict = at.Engine(tokens=[], current_release=frozenset(), strict=True)
    hits = [h for h in strict.scan(NOTES.decode(), at.RELEASE_NOTES_PATH) if h.rule == "R2" and h.line == 3]
    assert [h.matched for h in hits] == ["1.5.0"]


def test_history_strict_fallback_reports_current_declaration(tmp_path):
    hits = _history({"pyproject.toml": PYPROJECT, "config/audit_allowlist.yaml": b"allowlist: [\n",
                     at.RELEASE_NOTES_PATH: NOTES}, tmp_path)
    assert _context(hits, "config/audit_allowlist.yaml")
    assert _declaration(hits)
