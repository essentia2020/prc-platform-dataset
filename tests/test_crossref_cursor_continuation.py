"""Crossref short-page continuation and cursor request invariants."""

import json
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest

from src.common.config import load_sources_config
from src.common.http import PoliteClient
from src.common.log import JsonlLogger
from src.common.raw_store import RawStore
from src.common.walk import CursorWalker
from src.extract.crossref_common import parse_crossref_page, url_builder
from src.extract.selectors import CrossrefScope
from tests.offline import make_run_config


def page(n, total, cursor=None):
    return {"status": "ok", "message": {"items": [{}] * n,
            "total-results": total, "next-cursor": cursor}}


def run_walk(tmp_path, payloads, scope=None, tolerance=0):
    sources = deepcopy(load_sources_config())
    sources["sources"]["crossref"]["pagination"]["rows"] = 3
    scope = scope or CrossrefScope("10.1099", "journal-article")
    build = url_builder(make_run_config(), sources, scope)
    responses = iter(payloads)
    requests = []

    def transport(url, *args):
        requests.append(url)
        return 200, {}, json.dumps(next(responses)).encode()

    logger = JsonlLogger("test", log_dir=tmp_path / "logs")
    client = PoliteClient(user_agent="offline", min_interval_seconds=0,
                          transport=transport, sleeper=lambda _: None)
    walker = CursorWalker(client=client, store=RawStore(tmp_path / "raw"),
                          manifest_root=tmp_path / "manifests", run_id="test",
                          source="crossref", scope=scope.scope_id, logger=logger,
                          total_tolerance=tolerance,
                          tolerance_reason="offline fixture" if tolerance else "")
    walk = walker.run(build_url=build, parse_page=parse_crossref_page, initial_cursor="*")
    events = [json.loads(line) for line in logger.path.read_text().splitlines()]
    return walk, requests, events


@pytest.mark.parametrize("scope", [
    CrossrefScope("10.1099", "journal-article"),
    CrossrefScope("issn:2631-3952", "journal-article"),
])
def test_short_pages_continue_and_queries_repeat_with_immediate_cursor(tmp_path, scope):
    # Special characters must survive one URL encode/decode unchanged.
    cursors = ["next+/= &?%2F", "third/+==", "fourth%25"]
    payloads = [page(3, 6, cursors[0]), page(1, 6, cursors[1]),
                page(2, 6, cursors[2]), page(0, 6)]
    walk, requests, events = run_walk(tmp_path, payloads, scope)
    assert walk.state == "complete"
    assert len(requests) == len(walk.pages) == 4
    assert walk.items_total == 6
    assert walk.completion["terminal_evidence"] == "empty_page"
    queries = [parse_qs(urlsplit(url).query) for url in requests]
    assert [q["cursor"][0] for q in queries] == ["*", *cursors]
    original = {k: v for k, v in queries[0].items() if k != "cursor"}
    assert set(original) == {"filter", "rows", "select", "mailto"}
    assert original["rows"] == ["3"]
    expected_filter = ("issn:2631-3952" if scope.kind == "issn" else "prefix:10.1099")
    assert original["filter"] == [expected_filter + ",type:journal-article"]
    for query in queries:
        assert {k: v for k, v in query.items() if k != "cursor"} == original
    assert [p.cursor_in for p in walk.pages] == ["*", *cursors]
    assert [p.cursor_out for p in walk.pages[:-1]] == cursors
    short = [a for a in walk.anomalies if a["code"] == "short_page"]
    assert [(a["page"], a["items_in_page"], a["rows"]) for a in short] == [(2, 1, 3), (3, 2, 3)]
    logged = [e for e in events if e["event"] == "short_page"]
    assert [(e["page"], e["items_in_page"], e["rows"]) for e in logged] == [(2, 1, 3), (3, 2, 3)]


@pytest.mark.parametrize("payloads,state,evidence", [
    ([page(1, 4, "a"), page(3, 4, "b"), page(0, 4)], "complete", "empty_page"),
    ([page(1, 4, "a"), page(3, 4)], "complete", "no_next_cursor"),
    ([page(3, 5, "a"), page(2, 5)], "complete", "no_next_cursor"),
    ([page(1, 4, "a"), page(2, 4)], "failed", "no_next_cursor"),
    ([page(1, 4, "a"), page(2, 4, "b"), page(0, 4)], "failed", "empty_page"),
    ([page(0, 0, "unused")], "complete", "empty_page"),
    ([page(0, 1, "unused")], "failed", "empty_page"),
    # No heuristic page cap: a legitimate sequence may be mostly short pages.
    ([page(1, 12, f"c{i}") for i in range(12)] + [page(0, 12)], "complete", "empty_page"),
])
def test_exhaustion_and_item_total_both_required(tmp_path, payloads, state, evidence):
    walk, requests, _ = run_walk(tmp_path, payloads)
    assert len(requests) == len(payloads)
    assert walk.state == state
    assert walk.completion["terminal_evidence"] == evidence


@pytest.mark.parametrize("tolerance", [0, 2])
def test_matching_or_tolerated_running_total_does_not_end_a_short_page(tmp_path, tolerance):
    # The first page already matches the reported total but has a continuation.
    payloads = [page(2, 2, "next"), page(1, 2, "last"), page(0, 2)]
    walk, requests, _ = run_walk(tmp_path, payloads, tolerance=tolerance)
    assert len(requests) == 3
    assert walk.completion["total_delta"] == 1
    assert walk.state == ("complete" if tolerance else "failed")
