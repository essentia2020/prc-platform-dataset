"""Windowed cursor walks (D-045 option c, D-057).

A scope listed in ``pagination.windowed_scopes`` is walked per date window
at tolerance 0 and recorded as one composite walk whose completion requires
every window complete and the window totals equal to the unwindowed total
probed before and after the pass.  Offline fixtures only; nothing here
contacts a network service.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from src.common.config import load_sources_config
from src.common.interim import read_csv
from src.common.manifest import WINDOWED_RULE, list_walks, read_walk_manifest, walk_shape_issues
from src.common.windowed_walk import probe_scope_id
from src.common.windows import DateWindow, WindowError, date_windows, window_scope_id, windows_partition_axis
from src.extract import crossref_peer_reviews
from src.extract.crossref_common import ExtractionIncomplete, windowed_scope_config
from tests.offline import FixtureTransport, crossref_page, run_context
from tools import check_walk_shape

SCOPE = "works__10.5256__peer-review"
# The fixture review 10.5256/f1000research.1001.r5001 is issued 2022-06-06.
HIT_WINDOW = "from-issued-date:2022-04-01,until-issued-date:2022-06-30&rows=3&cursor=%2A"
PROBE = "filter=prefix:10.5256,type:peer-review&rows=0"


def _run(tmp_path: Path, transport=None, sources=None):
    run_config, loaded, platforms, logger, roots = run_context(tmp_path)
    sources = sources or loaded
    transport = transport or FixtureTransport()
    error = None
    try:
        outcomes = crossref_peer_reviews.run(run_config, sources, platforms, logger, transport=transport,
                                             sleeper=lambda s: None, **roots)
    except ExtractionIncomplete as exc:
        error = exc
        outcomes = []
    manifest = json.loads((roots["manifest_root"] / run_config.run_id / f"{run_config.run_id}.json").read_text())
    return run_config, roots, transport, manifest, error


def _composite(roots, run_config):
    walks = list_walks(roots["manifest_root"], run_config.run_id, "crossref", SCOPE)
    return walks


# ---------------------------------------------------------------- windows
def test_quarter_windows_partition_the_axis_with_guards():
    windows = date_windows("issued", "quarter", date(2012, 7, 1), date(2026, 9, 30))
    assert windows_partition_axis(windows)
    assert windows[0] == DateWindow("issued", None, date(2012, 6, 30))
    assert windows[1] == DateWindow("issued", date(2012, 7, 1), date(2012, 9, 30))
    assert windows[-2] == DateWindow("issued", date(2026, 7, 1), date(2026, 9, 30))
    assert windows[-1] == DateWindow("issued", date(2026, 10, 1), None)
    assert len(windows) == 2 + 4 * 14 + 1  # 2012Q3 .. 2026Q3 plus two guards
    assert windows[0].crossref_filter == "until-issued-date:2012-06-30"
    assert windows[1].crossref_filter == "from-issued-date:2012-07-01,until-issued-date:2012-09-30"
    assert windows[-1].crossref_filter == "from-issued-date:2026-10-01"
    assert windows[0].label == "issued_min_2012-06-30"
    assert window_scope_id(SCOPE, windows[1]) == f"{SCOPE}__issued_2012-07-01_2012-09-30"
    # February and leap years are handled by month-end arithmetic.
    monthly = date_windows("created", "month", date(2024, 1, 1), date(2024, 3, 1))
    assert [w.end for w in monthly[1:-1]] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)]
    assert monthly[1].crossref_filter == "from-created-date:2024-01-01,until-created-date:2024-01-31"


def test_window_configuration_errors_are_explicit():
    with pytest.raises(WindowError, match="first day of a quarter"):
        date_windows("issued", "quarter", date(2012, 8, 1), date(2026, 9, 30))
    with pytest.raises(WindowError, match="unknown window date_field"):
        date_windows("modified", "quarter", date(2012, 7, 1), date(2026, 9, 30))
    with pytest.raises(WindowError, match="granularity"):
        date_windows("issued", "week", date(2012, 7, 1), date(2026, 9, 30))
    with pytest.raises(WindowError, match="before first_window_start"):
        date_windows("issued", "quarter", date(2027, 1, 1), date(2026, 9, 30))
    assert not windows_partition_axis([DateWindow("issued", None, date(2012, 6, 30)),
                                       DateWindow("issued", date(2012, 7, 2), None)])


def test_shipped_windowed_scopes_are_pinned():
    pagination = load_sources_config()["sources"]["crossref"]["pagination"]
    windowed = pagination.get("windowed_scopes") or {}
    assert set(windowed) == {SCOPE}, "windowed scopes are decided per scope (D-057); document a new one first"
    entry = windowed[SCOPE]
    assert (entry["date_field"], entry["granularity"], str(entry["first_window_start"])) == \
        ("issued", "quarter", "2012-07-01")
    assert entry["reason"].strip()
    assert not set(windowed) & set(pagination.get("total_tolerance_overrides") or {})
    templates = load_sources_config()["sources"]["crossref"]["query_templates"]
    assert "{window_filter}" in templates["works_by_prefix_type_and_window"]
    assert "rows=0" in templates["works_total_by_prefix_and_type"]


def test_windowed_scope_may_not_also_carry_a_tolerance_override():
    sources = load_sources_config()
    pagination = sources["sources"]["crossref"]["pagination"]
    pagination["total_tolerance_overrides"] = {SCOPE: {"total_tolerance": 25, "reason": "x"}}
    with pytest.raises(ExtractionIncomplete, match="both windowed_scopes and total_tolerance_overrides"):
        windowed_scope_config(pagination, SCOPE)
    pagination["total_tolerance_overrides"] = {}
    pagination["windowed_scopes"][SCOPE].pop("reason")
    with pytest.raises(ExtractionIncomplete, match="reason"):
        windowed_scope_config(pagination, SCOPE)
    assert windowed_scope_config(pagination, "works__10.12688__journal-article") is None


# ------------------------------------------------------------ happy path
def test_windowed_scope_completes_as_a_composite_walk(tmp_path: Path):
    run_config, roots, transport, manifest, error = _run(tmp_path)
    assert error is None
    walks = _composite(roots, run_config)
    assert [w.walk_id for w in walks] == ["w01"], "window walks are not listed under the parent scope"
    walk = walks[0]
    assert walk.is_complete
    completion = walk.completion
    assert completion["rule"] == WINDOWED_RULE
    assert completion["total_tolerance"] == 0
    assert completion["window_count"] == len(completion["windows"]) == 59
    assert all(w["state"] == "complete" and w["total_delta"] == 0 for w in completion["windows"])
    assert completion["unwindowed_total_before"] == completion["unwindowed_total_after"] == 1
    assert completion["sum_of_window_totals"] == 1
    assert completion["partition_delta_before"] == completion["partition_delta_after"] == 0
    assert completion["first_page_total_results"] == 1 and completion["total_delta"] == 0
    assert completion["probe_before"]["response_path"].startswith(f"crossref/{probe_scope_id(SCOPE)}/")
    assert (roots["raw_root"] / completion["probe_before"]["response_path"]).is_file()
    assert (roots["raw_root"] / completion["probe_after"]["response_path"]).is_file()
    # Composite pages are the window pages renumbered, with window provenance on each line.
    assert [p.page for p in walk.pages] == list(range(1, len(walk.pages) + 1))
    lines = [json.loads(line) for line in (roots["manifest_root"] / run_config.run_id
                                            / f"crossref__{SCOPE}__w01.manifest.jsonl").read_text().splitlines()]
    pages = [line for line in lines if line["record"] == "page"]
    hit = [p for p in pages if p["items_in_page"] == 1]
    assert len(hit) == 1 and hit[0]["window"] == "issued_2022-04-01_2022-06-30"
    assert hit[0]["window_walk_id"] == "w01" and hit[0]["window_page"] == 1
    assert hit[0]["response_path"].startswith(f"crossref/{SCOPE}__issued_2022-04-01_2022-06-30/")
    # Each window walked once under its own sub-scope at tolerance 0.
    sub = read_walk_manifest(roots["manifest_root"] / run_config.run_id
                             / f"crossref__{SCOPE}__issued_2022-04-01_2022-06-30__w01.manifest.jsonl")
    assert sub.is_complete and sub.completion["total_tolerance"] == 0 and sub.scope.endswith("2022-06-30")
    urls = [r["url"] for r in transport.requests if "10.5256" in r["url"]]
    assert sum(1 for u in urls if PROBE in u) == 2
    assert sum(1 for u in urls if "from-issued-date:" in u or "until-issued-date:" in u) == 60  # 59 windows + 1 page
    assert not any("cursor" in u for u in urls if PROBE in u)
    # The flattened interim is unchanged in content.
    rows = read_csv(roots["interim_root"] / "crossref_peer_reviews__f1000research.csv")
    assert sorted({r["doi"] for r in rows}) == ["10.5256/f1000research.1001.r5001"]
    assert {r["walk_id"] for r in rows} == {"w01"}


def test_run_manifest_records_the_window_set_and_window_scopes(tmp_path: Path):
    run_config, roots, _, manifest, _ = _run(tmp_path)
    entry = manifest["scopes"][f"crossref/{SCOPE}"]
    assert entry["extraction_status"] == "complete" and entry["selected_walk_id"] == "w01"
    window_set = entry["window_set"]
    assert (window_set["date_field"], window_set["granularity"], window_set["first_window_start"]) == \
        ("issued", "quarter", "2012-07-01")
    assert window_set["reason"].strip()
    assert len(window_set["windows"]) == 59
    assert window_set["windows"][0] == {"label": "issued_min_2012-06-30", "date_field": "issued",
                                        "from": None, "until": "2012-06-30"}
    assert entry["software"]["git_commit"]
    sub_keys = [k for k in manifest["scopes"] if k.startswith(f"crossref/{SCOPE}__issued_")]
    assert len(sub_keys) == 59
    sub = manifest["scopes"][f"crossref/{SCOPE}__issued_2022-04-01_2022-06-30"]
    assert sub["window_of"] == SCOPE and sub["extraction_status"] == "complete"
    assert sub["window"]["from"] == "2022-04-01" and sub["items"] == 1


def test_complete_composite_is_reused_on_the_next_invocation(tmp_path: Path):
    run_config, roots, transport, _, _ = _run(tmp_path)
    first = len(transport.requests)
    _run(tmp_path, transport=transport)
    assert not any("10.5256" in r["url"] for r in transport.requests[first:])
    assert [w.walk_id for w in _composite(roots, run_config)] == ["w01"]


def test_composite_passes_the_walk_shape_check(tmp_path: Path):
    run_config, roots, _, _, _ = _run(tmp_path)
    walk = _composite(roots, run_config)[0]
    assert walk_shape_issues(walk, 3, roots["raw_root"]) == []
    reports, errors = check_walk_shape.run_check(run_config.run_id, roots["manifest_root"], roots["raw_root"], 3,
                                                 [SCOPE, f"{SCOPE}__issued_2022-04-01_2022-06-30"], False, True)
    assert errors == []
    by_scope = {r.scope: r for r in reports}
    assert by_scope[SCOPE].composite and by_scope[SCOPE].windows == 59 and by_scope[SCOPE].issues == []
    assert not by_scope[f"{SCOPE}__issued_2022-04-01_2022-06-30"].composite
    assert check_walk_shape.exit_status(reports, errors) == 0
    # A composite whose window list disagrees with its totals is an issue, not a pass.
    tampered = deepcopy(walk)
    tampered.completion["windows"][5]["state"] = "failed"
    tampered.completion["unwindowed_total_after"] = 2
    issues = walk_shape_issues(tampered, 3, None)
    assert any("not complete" in i for i in issues) and any("unwindowed_total_after is 2" in i for i in issues)


# --------------------------------------------------------------- failures
def test_window_cursor_loss_fails_the_scope_at_tolerance_zero(tmp_path: Path):
    lost = {"status": "ok", "message": {"items": [{"DOI": "10.5256/f1000research.1001.r5001", "type": "peer-review",
                                                   "issued": {"date-parts": [[2022, 6, 6]]}}],
                                        "total-results": 2, "next-cursor": "CURSOR-DATA-2"}}
    transport = FixtureTransport(scripted={HIT_WINDOW: [crossref_page(200, lost)] * 3})
    run_config, roots, transport, manifest, error = _run(tmp_path, transport=transport)
    assert error is not None and SCOPE in str(error)
    walks = _composite(roots, run_config)
    assert [w.state for w in walks] == ["failed"]
    reason = walks[0].reason
    assert "1 of 59 window walk(s) not complete at tolerance 0" in reason
    assert "issued_2022-04-01_2022-06-30" in reason and "delta -1" in reason
    window_walks = list_walks(roots["manifest_root"], run_config.run_id, "crossref",
                              f"{SCOPE}__issued_2022-04-01_2022-06-30")
    assert [w.walk_id for w in window_walks] == ["w01", "w02", "w03"]
    assert all(w.state == "failed" for w in window_walks)
    assert manifest["scopes"][f"crossref/{SCOPE}"]["extraction_status"] == "failed"
    assert not (roots["interim_root"] / "crossref_peer_reviews__f1000research.csv").exists()
    # The window pages are still listed so the evidence of the failed pass stays reachable.
    assert walks[0].completion["windows"][0]["state"] == "complete"
    assert walks[0].completion["probe_after"]["total_results"] == 1


def test_partition_mismatch_fails_the_scope(tmp_path: Path):
    bigger = {"status": "ok", "message": {"items": [], "total-results": 2, "next-cursor": None}}
    transport = FixtureTransport(scripted={PROBE: [crossref_page(200, bigger), crossref_page(200, bigger)]})
    run_config, roots, _, manifest, error = _run(tmp_path, transport=transport)
    assert error is not None
    walk = _composite(roots, run_config)[0]
    assert walk.state == "failed"
    assert "window totals sum to 1 but the unwindowed total-results is 2 before and 2 after" in walk.reason
    assert walk.completion["partition_delta_before"] == -1
    assert walk.completion["sum_of_window_totals"] == 1
    assert walk_shape_issues(walk, 3, None) == []  # not complete -> not judged


def test_moving_unwindowed_total_fails_the_scope(tmp_path: Path):
    bigger = {"status": "ok", "message": {"items": [], "total-results": 2, "next-cursor": None}}
    transport = FixtureTransport(scripted={PROBE: [crossref_page(200, bigger)]})  # second probe from the fixture
    run_config, roots, _, _, error = _run(tmp_path, transport=transport)
    walk = _composite(roots, run_config)[0]
    assert walk.state == "failed"
    assert "moved during the pass (2 -> 1)" in walk.reason
    assert walk.completion["total_results_moved_during_walk"] is True


def test_failed_probe_fails_the_scope_without_walking_windows(tmp_path: Path):
    transport = FixtureTransport(scripted={PROBE: [crossref_page(400, {"status": "error"})]})
    run_config, roots, transport, _, error = _run(tmp_path, transport=transport)
    walk = _composite(roots, run_config)[0]
    assert walk.state == "failed" and "probe failed before the window pass" in walk.reason
    assert not any("from-issued-date" in r["url"] for r in transport.requests)
    assert walk.completion["windows"] == [] and walk.pages == []


def test_failed_pass_is_followed_by_a_fresh_pass(tmp_path: Path):
    bigger = {"status": "ok", "message": {"items": [], "total-results": 2, "next-cursor": None}}
    transport = FixtureTransport(scripted={PROBE: [crossref_page(200, bigger), crossref_page(200, bigger)]})
    run_config, roots, transport, _, error = _run(tmp_path, transport=transport)
    assert error is not None
    _, _, _, manifest, error = _run(tmp_path, transport=transport)
    assert error is None
    walks = _composite(roots, run_config)
    assert [(w.walk_id, w.state) for w in walks] == [("w01", "failed"), ("w02", "complete")]
    assert manifest["scopes"][f"crossref/{SCOPE}"]["selected_walk_id"] == "w02"
    window_walks = list_walks(roots["manifest_root"], run_config.run_id, "crossref",
                              f"{SCOPE}__issued_2022-04-01_2022-06-30")
    assert [w.walk_id for w in window_walks] == ["w01", "w02"]  # every pass walks every window afresh
