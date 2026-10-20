"""Shared pytest fixtures.

Placeholder R1 tokens used in the audit tests are synthetic strings; real
tokens live only in the local token file referenced by ``PRC_AUDIT_TOKENS``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import socket

from tools import audit_text

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    """Every test must use an offline transport."""
    def blocked(*args, **kwargs):
        raise AssertionError("network disabled in tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)

PLACEHOLDER_TOKENS = (
    "placeholdertokenalpha",
    "placeholder phrase beta",
    "PTX1",
    "PLH-2",
)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def placeholder_tokens_file(tmp_path: Path) -> Path:
    path = tmp_path / "placeholder.audit_tokens.txt"
    path.write_text("# placeholder tokens\n" + "\n".join(PLACEHOLDER_TOKENS) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def engine(placeholder_tokens_file: Path) -> audit_text.Engine:
    tokens = audit_text.load_tokens(str(placeholder_tokens_file), env_path="")
    return audit_text.Engine(tokens=tokens, allowlist=[])


@pytest.fixture
def engine_factory(placeholder_tokens_file: Path):
    def make(allowlist=None) -> audit_text.Engine:
        tokens = audit_text.load_tokens(str(placeholder_tokens_file), env_path="")
        return audit_text.Engine(tokens=tokens, allowlist=list(allowlist or []))
    return make


@pytest.fixture(scope="session")
def real_tokens_path() -> str | None:
    return os.environ.get(audit_text.TOKENS_ENV)


# ----------------------------------------------------------- pipeline runs
@pytest.fixture(scope="session")
def pipeline_outputs(tmp_path_factory):
    """One complete offline run: extraction → normalisation → analysis → report.

    Shared by the Stage 4–6 tests; every network call is served by the
    fixture transport.  Returned object: ``tests.offline.PipelineOutputs``.
    """
    from tests.offline import run_full_pipeline
    return run_full_pipeline(tmp_path_factory.mktemp("pipeline"))


@pytest.fixture(scope="session")
def blocked_pipeline_outputs(tmp_path_factory):
    """Same run, but the F1000 journal-article scope fails (5 × HTTP 500)."""
    from tests.offline import FixtureTransport, crossref_page, run_full_pipeline
    transport = FixtureTransport(scripted={"prefix:10.12688,type:journal-article": [crossref_page(500)] * 5})
    return run_full_pipeline(tmp_path_factory.mktemp("pipeline_blocked"), transport=transport, expect_incomplete=True)
