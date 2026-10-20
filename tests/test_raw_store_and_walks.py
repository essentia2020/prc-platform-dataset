"""Raw-store immutability, manifests, walk states and cursor restarts (boundary tests 6 and 7)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from src.common.http import PoliteClient
from src.common.manifest import (ManifestError, WalkManifestWriter, list_walks, read_walk_manifest, select_walk,
                                 update_run_manifest_scope, verify_walk_against_store, walk_manifest_path)
from src.common.raw_store import RawStore, RawStoreError
from src.common.walk import CursorWalker, ParsedPage, close_stale_walks
from tests.offline import FixtureTransport, crossref_page
from src.extract.crossref_common import parse_crossref_page

RUN = "run_test_01"


def _client(transport, **kw) -> PoliteClient:
    return PoliteClient(user_agent="tests/1.4.0 (mailto:offline@example.invalid)", backoff_seconds=[0, 0, 0, 0, 0],
                        min_interval_seconds=0, sleeper=lambda s: None, transport=transport, **kw)


def _parse(body: bytes) -> ParsedPage:
    return parse_crossref_page(body)


def _url(prefix="10.32388", record_type="posted-content"):
    def build(cursor: str) -> str:
        return f"https://api.crossref.org/works?filter=prefix:{prefix},type:{record_type}&rows=3&cursor={cursor or '*'}"
    return build


# ------------------------------------------------------------------ raw store
def test_attempt_files_are_never_overwritten(tmp_path: Path):
    store = RawStore(tmp_path)
    paths = store.write_attempt("crossref", "scope", RUN, "w01", 1, 1, {"url": "u"}, b'{"a": 1}')
    assert paths.response_path.exists() and paths.request_path.exists()
    with gzip.open(paths.response_path, "rb") as handle:
        assert handle.read() == b'{"a": 1}'
    with pytest.raises(RawStoreError):
        store.write_attempt("crossref", "scope", RUN, "w01", 1, 1, {"url": "u"}, b"other")
    # the original bytes survive the refused write
    with gzip.open(paths.response_path, "rb") as handle:
        assert handle.read() == b'{"a": 1}'


def test_walk_ids_are_allocated_monotonically(tmp_path: Path):
    store = RawStore(tmp_path)
    assert store.new_walk_id("crossref", "scope", RUN) == "w01"
    store.write_attempt("crossref", "scope", RUN, "w01", 1, 1, {}, b"{}")
    assert store.new_walk_id("crossref", "scope", RUN) == "w02"
    assert store.new_walk_id("crossref", "scope", RUN, known=["w05"]) == "w06"


def test_gzip_output_is_deterministic(tmp_path: Path):
    store = RawStore(tmp_path)
    a = store.write_attempt("crossref", "s", RUN, "w01", 1, 1, {}, b"payload")
    b = store.write_attempt("crossref", "s", RUN, "w01", 2, 1, {}, b"payload")
    assert store.file_sha256(a.response_rel) == store.file_sha256(b.response_rel)


# ------------------------------------------------------------------ manifests
def test_manifest_is_append_only_and_never_resumed(tmp_path: Path):
    path = tmp_path / "m.jsonl"
    writer = WalkManifestWriter(path, RUN, "crossref", "scope", "w01")
    writer.close("complete")
    with pytest.raises(ManifestError):
        WalkManifestWriter(path, RUN, "crossref", "scope", "w01")
    record = read_walk_manifest(path)
    assert record.state == "complete" and record.pages == []


def test_select_walk_requires_a_complete_walk(tmp_path: Path):
    paths = []
    for walk_id, state, ended in [("w01", "incomplete_restarted", "2026-10-20T10:00:00Z"),
                                  ("w02", "complete", "2026-10-20T11:00:00Z"),
                                  ("w03", "complete", "2026-10-20T11:00:00Z"),
                                  ("w04", "failed", "2026-10-20T12:00:00Z")]:
        p = tmp_path / f"{walk_id}.jsonl"
        clock = iter(["2026-10-20T09:00:00Z", ended])
        w = WalkManifestWriter(p, RUN, "crossref", "scope", walk_id, now=lambda: next(clock))
        w.close(state)
        paths.append(p)
    walks = [read_walk_manifest(p) for p in paths]
    chosen, reason = select_walk(walks, "latest_completed_then_smallest_walk_id")
    assert chosen.walk_id == "w02" and "smallest walk_id" in reason
    none, reason = select_walk([walks[0], walks[3]], "latest_completed_then_smallest_walk_id")
    assert none is None and reason.startswith("no complete walk")
    with pytest.raises(ManifestError):
        select_walk(walks, "any_other_policy")


# ---------------------------------------------------------------------- walks
def test_complete_walk_records_every_page_with_matching_digest(tmp_path: Path):
    transport = FixtureTransport()
    store = RawStore(tmp_path / "raw")
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope="works__10.32388__posted-content")
    walk = walker.run(build_url=_url(), parse_page=_parse, initial_cursor="*")
    assert walk.state == "complete"
    assert [p.page for p in walk.pages] == [1, 2, 3]
    assert [p.items_in_page for p in walk.pages] == [3, 3, 0]
    assert walk.pages[0].cursor_out == "CURSOR-QPC-2" and walk.pages[-1].cursor_out == ""
    assert verify_walk_against_store(walk, store.root) == []
    # a second invocation reuses the complete walk without any request
    before = len(transport.requests)
    again = walker.run(build_url=_url(), parse_page=_parse, initial_cursor="*")
    assert again.walk_id == walk.walk_id and len(transport.requests) == before


def test_retry_then_accept_keeps_rejected_attempt_on_disk(tmp_path: Path):
    transport = FixtureTransport(scripted={"cursor=*": [crossref_page(503, headers={"retry-after": "0"}),
                                                        crossref_page(200, body=b"not json")]})
    store = RawStore(tmp_path / "raw")
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope="works__10.32388__journal-article")
    walk = walker.run(build_url=_url(record_type="journal-article"), parse_page=_parse, initial_cursor="*")
    assert walk.state == "complete" and walk.pages[0].accepted_attempt == 3
    page_dir = store.walk_dir("crossref", "works__10.32388__journal-article", RUN, walk.walk_id) / "page_1"
    assert sorted(p.name for p in page_dir.iterdir()) == [
        "attempt_1.request.json", "attempt_1.response.json.gz", "attempt_2.request.json",
        "attempt_2.response.json.gz", "attempt_3.request.json", "attempt_3.response.json.gz"]
    lines = [json.loads(l) for l in walk_manifest_path(tmp_path / "m", RUN, "crossref",
                                                        "works__10.32388__journal-article", walk.walk_id).read_text().splitlines()]
    assert [l["record"] for l in lines] == ["walk_header", "rejected_attempt", "rejected_attempt",
                                          "page", "anomaly", "walk_end"]


def test_exhausted_attempts_fail_the_walk_and_write_no_count(tmp_path: Path):
    transport = FixtureTransport(scripted={"cursor=*": [crossref_page(500)] * 5})
    store = RawStore(tmp_path / "raw")
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope="works__10.32388__journal-article")
    walk = walker.run(build_url=_url(record_type="journal-article"), parse_page=_parse, initial_cursor="*")
    assert walk.state == "failed" and walk.pages == []
    chosen, _ = select_walk(list_walks(tmp_path / "m", RUN, "crossref", "works__10.32388__journal-article"),
                            "latest_completed_then_smallest_walk_id")
    assert chosen is None


def test_cursor_rejection_restarts_in_a_new_walk(tmp_path: Path):
    # page 2 of the first walk is rejected with a definitive 400 -> incomplete_restarted;
    # the new walk starts again from the initial cursor and completes.
    transport = FixtureTransport(scripted={"cursor=CURSOR-QPC-2": [crossref_page(400, {"status": "error"})]})
    store = RawStore(tmp_path / "raw")
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope="works__10.32388__posted-content")
    walk = walker.run(build_url=_url(), parse_page=_parse, initial_cursor="*")
    walks = list_walks(tmp_path / "m", RUN, "crossref", "works__10.32388__posted-content")
    assert [(w.walk_id, w.state) for w in walks] == [("w01", "incomplete_restarted"), ("w02", "complete")]
    assert walk.walk_id == "w02" and len(walk.pages) == 3
    assert walks[0].pages and walks[0].pages[0].page == 1  # page 1 of w01 is kept, never re-fetched into w01
    assert store.walk_dir("crossref", "works__10.32388__posted-content", RUN, "w01").is_dir()
    chosen, _ = select_walk(walks, "latest_completed_then_smallest_walk_id")
    assert chosen.walk_id == "w02"


def test_source_reported_cursor_error_restarts(tmp_path: Path):
    body = (Path(__file__).parent / "fixtures" / "crossref" / "error_cursor.json").read_bytes()
    transport = FixtureTransport(scripted={"cursor=CURSOR-QPC-2": [crossref_page(200, body=body)]})
    store = RawStore(tmp_path / "raw")
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope="works__10.32388__posted-content")
    walk = walker.run(build_url=_url(), parse_page=_parse, initial_cursor="*")
    states = [w.state for w in list_walks(tmp_path / "m", RUN, "crossref", "works__10.32388__posted-content")]
    assert states == ["incomplete_restarted", "complete"] and walk.state == "complete"


def test_restart_budget_is_bounded(tmp_path: Path):
    transport = FixtureTransport(scripted={"cursor=CURSOR-QPC-2": [crossref_page(400, {})] * 10})
    store = RawStore(tmp_path / "raw")
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope="works__10.32388__posted-content", max_restarts=2)
    walk = walker.run(build_url=_url(), parse_page=_parse, initial_cursor="*")
    assert walk.state == "incomplete_restarted"
    assert len(list_walks(tmp_path / "m", RUN, "crossref", "works__10.32388__posted-content")) == 3


def test_stale_in_progress_walk_is_closed_not_resumed(tmp_path: Path):
    root = tmp_path / "m"
    WalkManifestWriter(walk_manifest_path(root, RUN, "crossref", "s", "w01"), RUN, "crossref", "s", "w01")
    assert close_stale_walks(root, RUN, "crossref", "s") == ["w01"]
    walks = list_walks(root, RUN, "crossref", "s")
    assert walks[0].state == "incomplete_restarted"
    assert close_stale_walks(root, RUN, "crossref", "s") == []


def test_run_manifest_reports_scope_status(tmp_path: Path):
    transport = FixtureTransport()
    store = RawStore(tmp_path / "raw")
    scope = "works__10.32388__posted-content"
    walker = CursorWalker(client=_client(transport), store=store, manifest_root=tmp_path / "m", run_id=RUN,
                          source="crossref", scope=scope)
    walker.run(build_url=_url(), parse_page=_parse, initial_cursor="*")
    payload = update_run_manifest_scope(tmp_path / "m" / RUN / f"{RUN}.json", run_id=RUN, cutoff="2026-09-30",
                                        policy="latest_completed_then_smallest_walk_id", source="crossref",
                                        scope=scope, walks=list_walks(tmp_path / "m", RUN, "crossref", scope))
    entry = payload["scopes"][f"crossref/{scope}"]
    assert entry["extraction_status"] == "complete" and entry["selected_walk_id"] == "w01" and entry["items"] == 6


def test_rate_limit_headers_tighten_the_interval():
    transport = FixtureTransport(scripted={"cursor=*": [crossref_page(200, {"status": "ok", "message": {"items": []}},
                                                                      headers={"x-rate-limit-limit": "10",
                                                                               "x-rate-limit-interval": "5s"})]})
    client = _client(transport)
    client.get_page(_url()("*"))
    assert client.min_interval == pytest.approx(0.5)


def test_user_agent_carries_the_mailto_contact():
    transport = FixtureTransport()
    client = _client(transport)
    client.get_page(_url()("*"))
    assert transport.requests[0]["headers"]["User-Agent"].startswith("tests/1.4.0 (mailto:")


def test_transport_errors_are_retried_then_reported():
    transport = FixtureTransport(scripted={"cursor=*": [ConnectionError("boom")] * 5})
    client = _client(transport)
    result = client.get_page(_url()("*"))
    assert result.accepted is None and len(result.attempts) == 5
    assert all(a.status is None and "ConnectionError" in a.rejection_reason for a in result.attempts)
