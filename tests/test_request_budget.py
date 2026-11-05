"""Request budget of the polite client (``max_requests`` / ``PRC_MAX_REQUESTS``).

A replay of stored walks is expected to make no request. With
``PRC_MAX_REQUESTS=0`` that expectation is enforced: the first request is
refused before the transport is called, the stage stops, and the refusal is
in the log. A run whose walks are complete is reused without a request and
is therefore unaffected by a zero budget.
"""

import json

import pytest

from src.common.http import PoliteClient, RequestBudgetExhausted, request_budget_from_env
from src.common.register import load_platforms
from src.extract import crossref_works
from tests.offline import FixtureTransport, run_context


def copernicus():
    return next(r for r in load_platforms() if r["row_id"].startswith("copernicus"))


def _client(transport, **kw):
    return PoliteClient(user_agent="tests/1.4.0 (mailto:offline@example.invalid)", backoff_seconds=[0] * 5,
                        transport=transport, sleeper=lambda _: None, **kw)


def test_budget_refuses_before_the_transport_is_called():
    calls = []

    def transport(url, headers, timeout):
        calls.append(url)
        return 200, {}, b"{}"

    client = _client(transport, max_requests=1)
    assert client.get_page("https://example.invalid/1").accepted is not None
    assert client.requests_made == 1
    with pytest.raises(RequestBudgetExhausted):
        client.get_page("https://example.invalid/2")
    assert calls == ["https://example.invalid/1"]


def test_every_attempt_counts_against_the_budget():
    def transport(url, headers, timeout):
        return 503, {}, b""

    client = _client(transport, max_requests=3, max_attempts_per_page=5)
    with pytest.raises(RequestBudgetExhausted):
        client.get_page("https://example.invalid/retry")
    assert client.requests_made == 3


def test_budget_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("PRC_MAX_REQUESTS", raising=False)
    assert request_budget_from_env() is None
    assert _client(lambda *a: (200, {}, b"{}")).max_requests is None
    monkeypatch.setenv("PRC_MAX_REQUESTS", "0")
    assert request_budget_from_env() == 0
    client = _client(lambda *a: (200, {}, b"{}"))
    assert client.max_requests == 0
    with pytest.raises(RequestBudgetExhausted):
        client.get_page("https://example.invalid/none")
    assert client.requests_made == 0
    monkeypatch.setenv("PRC_MAX_REQUESTS", "none")
    with pytest.raises(ValueError):
        request_budget_from_env()


def test_zero_budget_stops_a_fresh_walk_and_passes_a_reused_one(tmp_path, monkeypatch):
    config, sources, _, logger, roots = run_context(tmp_path)
    rows = [copernicus()]
    monkeypatch.setenv("PRC_MAX_REQUESTS", "0")
    fresh = FixtureTransport()
    with pytest.raises(RequestBudgetExhausted):
        crossref_works.run(config, sources, rows, logger, transport=fresh, sleeper=lambda _: None, **roots)
    assert fresh.requests == []
    events = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()]
    assert any(e["event"] == "request_budget_exhausted" and e["max_requests"] == 0 for e in events)

    monkeypatch.delenv("PRC_MAX_REQUESTS")
    full = FixtureTransport()
    crossref_works.run(config, sources, rows, logger, transport=full, sleeper=lambda _: None, **roots)
    assert full.requests  # the complete walks of the run

    monkeypatch.setenv("PRC_MAX_REQUESTS", "0")
    replay = FixtureTransport()
    crossref_works.run(config, sources, rows, logger, transport=replay, sleeper=lambda _: None, **roots)
    assert replay.requests == []  # every scope reused its complete walk; the zero budget was never touched
