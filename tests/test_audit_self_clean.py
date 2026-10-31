"""The audit engine passes on its own repository.

The real token file is referenced by the ``PRC_AUDIT_TOKENS`` environment
variable (a path outside the repository).  A missing, empty or zero-token
file is a test FAILURE, never a skip: the self-audit is meaningless without
R1 tokens.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import audit_text


def _require_tokens(real_tokens_path: str | None) -> Path:
    if not real_tokens_path:
        pytest.fail(f"{audit_text.TOKENS_ENV} is not set; point it at the local token file outside the repository")
    path = Path(real_tokens_path)
    if not path.is_file():
        pytest.fail(f"token file not found: {path}")
    if path.stat().st_size == 0:
        pytest.fail(f"token file is empty: {path}")
    return path


def test_token_file_has_tokens(real_tokens_path):
    path = _require_tokens(real_tokens_path)
    tokens = audit_text.load_tokens(str(path), env_path=str(path))
    assert tokens, "token file contains zero tokens"


def test_working_tree_has_zero_unresolved_hits(real_tokens_path, repo_root):
    path = _require_tokens(real_tokens_path)
    hits = audit_text.run_audit(str(path), history=False, root=repo_root)
    assert hits == [], "\n".join(h.format() for h in hits)


def test_conflicting_token_paths_fail(tmp_path, real_tokens_path):
    path = _require_tokens(real_tokens_path)
    other = tmp_path / "other.audit_tokens.txt"
    other.write_text("placeholdertokenalpha\n", encoding="utf-8")
    with pytest.raises(audit_text.AuditConfigError, match="different files"):
        audit_text.load_tokens(str(other), env_path=str(path))


def test_empty_token_file_is_rejected(tmp_path):
    empty = tmp_path / "empty.audit_tokens.txt"
    empty.write_text("# comments only\n\n", encoding="utf-8")
    with pytest.raises(audit_text.AuditConfigError, match="no tokens"):
        audit_text.load_tokens(str(empty), env_path="")


def test_missing_token_file_is_rejected(tmp_path):
    with pytest.raises(audit_text.AuditConfigError, match="not found"):
        audit_text.load_tokens(str(tmp_path / "absent.txt"), env_path="")


def test_read_text_normalises_line_endings():
    assert audit_text.read_text(b"first line\r\nsecond line\r\n") == "first line\nsecond line\n"
    assert audit_text.read_text(b"a\rb") == "a\nb"
    assert audit_text.read_text(b"\0binary") is None
