"""Walk shape: total_delta == 0 is necessary, the page sequence is the proof.

A cursor reset re-serves pages. The observables are a repeated ``cursor_in``,
more non-empty pages than ``ceil(total-results / rows)``, a short page before
the last non-empty page, an empty page before the terminal one, or a record
accepted on two pages. ``walk_shape_issues`` reports them from the manifest
and the raw store without changing any walk state.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.common.manifest import (PageEntry, WalkRecord, expected_pages, list_walks, walk_shape_issues)
from tests.offline import run_full_pipeline


def _page(n: int, items: int, cursor_in: str, cursor_out: str, path: str = "") -> PageEntry:
    return PageEntry(page=n, accepted_attempt=1, response_path=path or f"p{n}.json", sha256="", bytes=0,
                     http_status=200, cursor_in=cursor_in, cursor_out=cursor_out, items_in_page=items,
                     accepted_at_utc="")


def _walk(pages: list[PageEntry], first_total: int, state: str = "complete") -> WalkRecord:
    items = sum(p.items_in_page for p in pages)
    return WalkRecord("run_x", "w01", "crossref", "works__10.1__journal-article", pages=pages, state=state,
                      completion={"first_page_total_results": first_total, "accepted_items_total": items,
                                  "last_page_total_results": first_total, "total_delta": items - first_total})


def test_expected_pages():
    assert expected_pages(0, 1000) == 0
    assert expected_pages(1, 1000) == 1
    assert expected_pages(1000, 1000) == 1
    assert expected_pages(1001, 1000) == 2
    assert expected_pages(None, 1000) is None


def test_consistent_walks_have_no_issues():
    # terminal short page
    w = _walk([_page(1, 1000, "*", "c2"), _page(2, 1000, "c2", "c3"), _page(3, 605, "c3", "c4")], 2605)
    assert walk_shape_issues(w, 1000) == []
    # terminal empty page after a full last page
    w = _walk([_page(1, 1000, "*", "c2"), _page(2, 1000, "c2", "c3"), _page(3, 0, "c3", "")], 2000)
    assert walk_shape_issues(w, 1000) == []
    # empty result set: one empty page
    assert walk_shape_issues(_walk([_page(1, 0, "*", "")], 0), 1000) == []


def test_reset_is_visible_even_when_total_delta_is_zero():
    # The cursor fell back to "*" after page 2; pages 3-4 repeat pages 1-2 and the
    # walk still ends with the right item count because deposits moved total-results
    # by exactly the re-served amount (the compensating case total_delta cannot see).
    pages = [_page(1, 1000, "*", "c2"), _page(2, 1000, "c2", "c3"),
             _page(3, 1000, "*", "c2"), _page(4, 1000, "c2", "c3"), _page(5, 500, "c3", "c4")]
    w = _walk(pages, 4500)
    assert w.completion["total_delta"] == 0
    issues = walk_shape_issues(w, 1000)
    assert any("cursor_in repeated" in i for i in issues)
    assert not any("non-empty page" in i for i in issues)     # 5 pages for 4,500 is arithmetically fine


def test_page_count_and_mid_walk_short_page_are_reported():
    w = _walk([_page(1, 1000, "*", "c2"), _page(2, 400, "c2", "c3"), _page(3, 1000, "c3", "c4")], 2400)
    issues = walk_shape_issues(w, 1000)
    assert any("short page 2" in i for i in issues)
    w = _walk([_page(1, 1000, "*", "c2"), _page(2, 1000, "c2", "c3"), _page(3, 1000, "c3", "c4"),
               _page(4, 0, "c4", "")], 2000)
    issues = walk_shape_issues(w, 1000)
    assert any("3 non-empty page(s) for total-results 2000" in i for i in issues)
    w = _walk([_page(1, 1000, "*", "c2"), _page(2, 0, "c2", "c3"), _page(3, 0, "c3", "")], 1000)
    assert any("empty page before the terminal page" in i for i in walk_shape_issues(w, 1000))


def test_duplicate_records_across_pages_are_read_from_the_raw_store(tmp_path: Path):
    for n, dois in ((1, ["10.1/a", "10.1/b"]), (2, ["10.1/b", "10.1/c"])):
        (tmp_path / f"p{n}.json").write_text(json.dumps({"message": {"items": [{"DOI": d} for d in dois]}}),
                                             encoding="utf-8")
    w = _walk([_page(1, 2, "*", "c2"), _page(2, 2, "c2", "c3")], 4)
    assert walk_shape_issues(w, 2) == []
    assert walk_shape_issues(w, 2, raw_root=tmp_path) == ["1 record(s) accepted on more than one page"]


def test_incomplete_walks_are_not_judged():
    w = _walk([_page(1, 1000, "*", "c2"), _page(2, 1000, "*", "c2")], 5000, state="failed")
    assert walk_shape_issues(w, 1000) == []


def test_offline_pipeline_walks_are_shape_consistent(tmp_path: Path):
    out = run_full_pipeline(tmp_path)
    manifest_root, raw_root = out.roots["manifest_root"], out.roots["raw_root"]
    run_id = out.run_config.run_id
    checked = 0
    for path in sorted(manifest_root.glob(f"{run_id}/crossref__*.manifest.jsonl")):
        scope = path.name.split("__", 1)[1].rsplit("__", 1)[0]
        for walk in list_walks(manifest_root, run_id, "crossref", scope):
            if walk.state != "complete":
                continue
            assert walk_shape_issues(walk, rows=3, raw_root=raw_root) == [], (scope, walk.walk_id)
            checked += 1
    assert checked > 5
