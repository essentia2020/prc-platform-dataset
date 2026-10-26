"""Requests the source rejects outright (HTTP 4xx other than 429).

Two guarantees:

* every element in ``select_fields`` is one the Crossref REST API accepts, so
  the first page of a walk cannot fail on request construction alone;
* a definitive rejection is made once, is never retried, is named as such in
  the walk manifest and the log, and keeps its response body in the raw store.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.config import load_sources_config
from src.common.manifest import load_run_manifest, run_manifest_path, software_record
from src.extract import crossref_works
from src.extract.crossref_common import ExtractionIncomplete
from tests.offline import FixtureTransport, crossref_page, run_context

# Elements the Crossref REST API lists as selectable on /works. The API
# returns this enumeration itself when an unknown element is requested
# (``/works?select=<unknown>``); the list is reproduced on the Crossref
# community forum,
# https://community.crossref.org/t/how-can-i-only-return-a-few-metadata-fields-instead-of-all-of-them-when-i-look-up-a-doi/4798
CROSSREF_SELECTABLE = {
    "abstract", "URL", "member", "posted", "score", "created", "degree", "update-policy",
    "short-title", "license", "ISSN", "container-title", "issued", "update-to", "issue", "prefix",
    "approved", "indexed", "article-number", "clinical-trial-number", "accepted", "author",
    "group-title", "DOI", "is-referenced-by-count", "updated-by", "event", "chair", "standards-body",
    "original-title", "funder", "translator", "published", "archive", "published-print",
    "alternative-id", "subject", "subtitle", "published-online", "publisher-location",
    "content-domain", "reference", "title", "link", "type", "publisher", "volume",
    "references-count", "ISBN", "issn-type", "assertion", "deposited", "page", "content-created",
    "short-container-title", "relation", "editor",
}

REJECTION_BODY = json.dumps({
    "status": "error", "message-type": "validation-failure",
    "message": [{"type": "parameter-not-allowed", "value": "subtype", "message": "not a selectable element"}],
}).encode()


def test_select_fields_are_all_selectable():
    pagination = load_sources_config()["sources"]["crossref"]["pagination"]
    select = pagination["select_fields"]
    assert select, "select_fields must not be empty"
    assert len(select) == len(set(select))
    unknown = sorted(set(select) - CROSSREF_SELECTABLE)
    assert unknown == [], f"not selectable on /works: {unknown}"
    # the fields the flattener reads must be requested
    for needed in ("DOI", "type", "title", "prefix", "member", "container-title", "group-title",
                   "created", "deposited", "indexed", "issued", "posted", "published-online",
                   "published-print", "relation"):
        assert needed in select


def test_definitive_rejection_is_not_retried(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = FixtureTransport({"api.crossref.org": [crossref_page(400, body=REJECTION_BODY)] * 50})
    with pytest.raises(ExtractionIncomplete):
        crossref_works.run(run_config, sources, platforms, logger, transport=transport,
                           sleeper=lambda s: None, **roots)
    # exactly one request per scope: a definitive answer is never retried
    scope_urls = {r["url"] for r in transport.requests}
    assert len(transport.requests) == len(scope_urls)

    manifest = load_run_manifest(run_manifest_path(roots["manifest_root"], run_config.run_id))
    assert manifest["scopes"], "run manifest must list the attempted scopes"
    for entry in manifest["scopes"].values():
        assert entry["extraction_status"] == "failed"
        assert entry["walk_states"] == {"w01": "failed"}
    walk_files = sorted(roots["manifest_root"].glob(f"{run_config.run_id}/crossref__works__*__w01.manifest.jsonl"))
    assert walk_files
    for path in walk_files:
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        closing = events[-1]
        assert closing["record"] == "walk_end" and closing["walk_state"] == "failed"
        assert "http 400 (definitive, not retried)" in closing["reason"]
        assert "attempt budget exhausted" not in closing["reason"]
        assert "response stored at" in closing["reason"]
        rejected = [e for e in events if e.get("record") == "rejected_attempt"]
        assert len(rejected) == 1 and rejected[0]["page"] == 1 and rejected[0]["attempt"] == 1
        stored = roots["raw_root"] / rejected[0]["response_path"]
        assert stored.exists(), "the rejection body must be kept for review"

    log_lines = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [e for e in log_lines if e["event"] == "http_attempt" and "outcome" in e]
    assert attempts and all(a["outcome"] == "rejected" and a["http_status"] == 400 for a in attempts)
    assert all("definitive, not retried" in a["reason"] for a in attempts)
    assert not any(a["outcome"] == "retry" for a in attempts)


def test_retryable_status_is_still_logged_as_retry(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = FixtureTransport({"prefix:10.1162,type:journal-article": [crossref_page(503)]})
    crossref_works.run(run_config, sources, platforms, logger, transport=transport,
                       sleeper=lambda s: None, **roots)
    log_lines = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [e for e in log_lines if e["event"] == "http_attempt" and "outcome" in e
                and e["scope"] == "works__10.1162__journal-article"]
    assert [a["outcome"] for a in attempts] == ["retry", "accepted"]


def test_software_record_is_populated(tmp_path: Path):
    record = software_record(tmp_path)  # not a Git repository
    assert record["python"] and record["platform"]
    assert record["git_commit"] == "unavailable"
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    crossref_works.run(run_config, sources, platforms, logger, transport=FixtureTransport(),
                       sleeper=lambda s: None, **roots)
    manifest = load_run_manifest(run_manifest_path(roots["manifest_root"], run_config.run_id))
    assert manifest["software"]["python"] == record["python"]
    assert manifest["software"]["git_commit"]


# --- total-results drift during a walk -------------------------------------

def _page(n, total, nxt=None):
    return {"status": "ok", "message": {"items": [{}] * n, "total-results": total, "next-cursor": nxt}}


def _walk_pages(tmp_path, payloads, tolerance=0, reason=""):
    from src.common.http import PoliteClient
    from src.common.log import JsonlLogger
    from src.common.raw_store import RawStore
    from src.common.walk import CursorWalker
    from src.extract.crossref_common import parse_crossref_page

    responses = iter(payloads)
    client = PoliteClient(user_agent="offline", min_interval_seconds=0,
                          transport=lambda *args: (200, {}, json.dumps(next(responses)).encode()),
                          sleeper=lambda _: None)
    logger = JsonlLogger("test", log_dir=tmp_path / "logs")
    walker = CursorWalker(client=client, store=RawStore(tmp_path / "raw"), manifest_root=tmp_path / "manifests",
                          run_id="test", source="crossref", scope="drift", total_tolerance=tolerance,
                          tolerance_reason=reason, logger=logger)
    walk = walker.run(build_url=lambda c: f"https://example.invalid/works?rows=3&cursor={c}",
                      parse_page=parse_crossref_page, initial_cursor="*")
    events = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return walk, events


def test_total_drift_failure_names_both_totals_and_is_logged(tmp_path):
    walk, events = _walk_pages(tmp_path, [_page(3, 3, "a"), _page(3, 4, "b"), _page(1, 8)])
    assert walk.state == "failed"
    assert walk.completion["first_page_total_results"] == 3
    assert walk.completion["last_page_total_results"] == 8
    assert walk.completion["total_results_moved_during_walk"] is True
    assert walk.completion["total_delta"] == 4
    assert "accepted item total 7 differs from first-page total-results 3 (delta +4, tolerance 0)" in walk.reason
    assert "moved during the walk" in walk.reason
    failed = [e for e in events if e["event"] == "walk_failed"]
    assert len(failed) == 1 and failed[0]["reason"] == walk.reason and failed[0]["page"] == 3


def test_stable_total_is_recorded_and_completion_logged(tmp_path):
    walk, events = _walk_pages(tmp_path, [_page(3, 4, "a"), _page(1, 4)])
    assert walk.state == "complete"
    assert walk.completion["total_results_moved_during_walk"] is False
    assert walk.completion["last_page_total_results"] == 4
    complete = [e for e in events if e["event"] == "walk_complete"]
    assert len(complete) == 1 and complete[0]["pages_accepted"] == 2 and complete[0]["items_total"] == 4


# --- per-scope tolerance ----------------------------------------------------

def test_scope_tolerance_defaults_and_overrides():
    from src.extract.crossref_common import scope_tolerance
    base = {"total_tolerance": 0, "tolerance_reason": "", "total_tolerance_overrides": {}}
    assert scope_tolerance(base, "works__10.5194__journal-article") == (0, "")
    with_override = {**base, "total_tolerance_overrides": {
        "works__10.5194__journal-article": {"total_tolerance": 2, "reason": "deposits land during the walk"}}}
    assert scope_tolerance(with_override, "works__10.5194__journal-article") == (2, "deposits land during the walk")
    assert scope_tolerance(with_override, "works__10.5194__posted-content") == (0, "")
    with pytest.raises(ExtractionIncomplete):
        scope_tolerance({**base, "total_tolerance_overrides": {"works__10.5194__journal-article": 2}},
                        "works__10.5194__journal-article")


PINNED_TOLERANCE_OVERRIDES = {
    "works__10.12688__journal-article": 50,
    "works__10.5194__posted-content": 25,
}


def test_shipped_config_tolerance_overrides_are_pinned():
    pagination = load_sources_config()["sources"]["crossref"]["pagination"]
    assert pagination["total_tolerance"] == 0
    overrides = pagination.get("total_tolerance_overrides") or {}
    assert set(overrides) == set(PINNED_TOLERANCE_OVERRIDES)
    for scope_id, entry in overrides.items():
        assert entry["total_tolerance"] == PINNED_TOLERANCE_OVERRIDES[scope_id]
        assert entry["reason"].strip(), scope_id


def test_override_is_applied_to_the_named_scope_only(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    sources["sources"]["crossref"]["pagination"]["total_tolerance_overrides"] = {
        "works__10.5194__journal-article": {"total_tolerance": 2, "reason": "offline test"}}
    crossref_works.run(run_config, sources, platforms, logger, transport=FixtureTransport(),
                       sleeper=lambda s: None, **roots)
    from src.common.manifest import read_walk_manifest
    root = roots["manifest_root"] / run_config.run_id
    tolerated = read_walk_manifest(root / "crossref__works__10.5194__journal-article__w01.manifest.jsonl")
    other = read_walk_manifest(root / "crossref__works__10.5194__posted-content__w01.manifest.jsonl")
    assert tolerated.completion["total_tolerance"] == 2 and tolerated.completion["tolerance_reason"] == "offline test"
    assert other.completion["total_tolerance"] == 0 and other.completion["tolerance_reason"] == ""
