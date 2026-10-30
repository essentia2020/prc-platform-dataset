"""tools/check_walk_shape.py rule 6 (D-058): zero-item Sciety walks against the docmaps index.

The index comes either from the run manifest (``sciety_index_snapshot``, as
written by the Sciety stage) or from a stored ``/docmaps/v1/index`` response
given with ``--sciety-index``.  Without either the Crossref rules behave as
before (tests/test_check_walk_shape_cli.py) and Sciety walks read
``index=not checked``.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.common.manifest import PageEntry, WalkManifestWriter, write_run_manifest
from tools import check_walk_shape

RUN = "run_test_02"
GROUP_URL = "https://sciety.org/groups/"
WALKS = {"review-commons": 0, "biophysics-colab": 0, "prereview": 1693}
INDEX = {"biophysics-colab": 32, "prereview": 1693}


def _walk(root: Path, slug: str, items: int, walk_id: str = "w01", state: str = "complete",
          scope: str | None = None) -> None:
    scope = scope or f"evaluations__{slug}"
    path = root / RUN / f"sciety__{scope}__{walk_id}.manifest.jsonl"
    writer = WalkManifestWriter(path, RUN, "sciety", scope, walk_id, now=lambda: "2026-10-28T00:00:00Z")
    writer.accept_page(PageEntry(page=1, accepted_attempt=1, response_path=f"sciety/{scope}/{RUN}/{walk_id}/p1.json.gz",
                                 sha256="", bytes=1, http_status=200, cursor_in="", cursor_out="",
                                 items_in_page=items, accepted_at_utc="2026-10-28T00:00:00Z"))
    writer.close(state, "test", pages_accepted=1, items_total=items, completion={"terminal_evidence": "empty_page"})


def _snapshot_file(path: Path, counts: dict[str, int], account_form=lambda slug: GROUP_URL + slug) -> None:
    articles = [{"publisher": {"account": {"id": account_form(slug)}}} for slug, n in counts.items() for _ in range(n)]
    path.write_text(json.dumps({"articles": articles}), encoding="utf-8")


def _run_manifest(root: Path, selected: dict[str, str], snapshot: dict[str, int] | None = None) -> None:
    payload = {"run_id": RUN, "scopes": {f"sciety/{scope}": {"selected_walk_id": w} for scope, w in selected.items()}}
    if snapshot is not None:
        payload["sciety_index_snapshot"] = {"scope": "index__all", "walk_id": "w01", "retrieved_at": "2026-10-28T05:10:00Z",
                                            "pages": 1, "docmaps_total": sum(snapshot.values()),
                                            "page_sha256": ["a" * 64],
                                            "groups": {GROUP_URL + slug: n for slug, n in snapshot.items()}}
    write_run_manifest(root / RUN / f"{RUN}.json", payload)


def _setup(tmp_path: Path, snapshot_in_manifest: dict[str, int] | None = None) -> Path:
    m = tmp_path / "manifests"
    for slug, items in WALKS.items():
        _walk(m, slug, items)
    _run_manifest(m, {f"evaluations__{slug}": "w01" for slug in WALKS}, snapshot_in_manifest)
    return m


def _args(m: Path, *extra: str) -> list[str]:
    return ["--run", RUN, "--manifest-root", str(m), "--no-raw", "--rows", "1000", *extra]


def test_index_file_counts_by_account_and_accepts_bare_list(tmp_path: Path):
    snap = tmp_path / "index.json"
    _snapshot_file(snap, {"prereview": 2, "ncrc": 1})
    index = check_walk_shape.load_sciety_index_file(snap)
    assert index.by_account == {GROUP_URL + "prereview": 2, GROUP_URL + "ncrc": 1}
    assert index.docmaps_total == 3 and index.sha256 and index.has_groups
    assert index.docmaps_for("evaluations__prereview") == 2
    assert index.docmaps_for("evaluations__review-commons") == 0
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps([{"publisher": {"account": {"id": GROUP_URL + "ncrc/"}}}]), encoding="utf-8")
    assert check_walk_shape.load_sciety_index_file(bare).by_account == {GROUP_URL + "ncrc": 1}


def test_group_identity_follows_the_register_not_only_the_slug(tmp_path: Path):
    # the live index names PREreview by its group id; the register maps both forms to one scope
    snap = tmp_path / "index.json"
    _snapshot_file(snap, {"10360d97-bf52-4aef-b2fa-2f60d319edd7": 3})
    index = check_walk_shape.load_sciety_index_file(snap)
    assert index.docmaps_for("evaluations__prereview") == 3


def test_zero_walk_of_indexed_group_is_an_issue_and_absent_group_is_explained(tmp_path: Path, capsys):
    m = _setup(tmp_path)
    snap = tmp_path / "index.json"
    _snapshot_file(snap, INDEX)
    assert check_walk_shape.main(_args(m, "--sciety-index", str(snap), "--json")) == 1
    payload = json.loads(capsys.readouterr().out)
    walks = {w["scope"]: w for w in payload["walks"]}
    rc = walks["evaluations__review-commons"]
    assert rc["index_coverage"] == "not_in_index" and rc["items_total"] == 0 and rc["issues"] == []
    bc = walks["evaluations__biophysics-colab"]
    assert bc["index_coverage"] == "in_index" and bc["index_docmaps"] == 32
    assert any("accepted 0 items" in i for i in bc["issues"])
    pr = walks["evaluations__prereview"]
    assert pr["issues"] == [] and pr["items_total"] == 1693 and pr["index_docmaps"] == 1693
    assert payload["sciety_index"]["groups"] == {GROUP_URL + "biophysics-colab": 32, GROUP_URL + "prereview": 1693}
    assert payload["sciety_index"]["sha256"]


def test_run_manifest_snapshot_is_used_without_a_flag(tmp_path: Path, capsys):
    m = _setup(tmp_path, snapshot_in_manifest=INDEX)
    assert check_walk_shape.main(_args(m)) == 1
    out = capsys.readouterr().out
    assert "sciety index (rule 6): run manifest sciety_index_snapshot (walk w01), 1725 docmaps" in out
    assert "sciety index coverage: 3 walk(s) checked, 1 explained zero(s), 1 with coverage issues" in out
    assert "index=not_in_index" in out and "index=in_index(32)" in out


def test_explicit_snapshot_overrides_the_run_manifest(tmp_path: Path, capsys):
    m = _setup(tmp_path, snapshot_in_manifest=INDEX)
    snap = tmp_path / "index.json"
    _snapshot_file(snap, {"prereview": 1693})          # biophysics-colab absent here: its zero is explained
    assert check_walk_shape.main(_args(m, "--sciety-index", str(snap))) == 0
    out = capsys.readouterr().out
    assert str(snap) in out and "2 explained zero(s), 0 with coverage issues" in out


def test_items_for_group_absent_from_snapshot_is_an_issue(tmp_path: Path, capsys):
    m = tmp_path / "manifests"
    _walk(m, "peerj", 368)
    _run_manifest(m, {"evaluations__peerj": "w01"})
    snap = tmp_path / "index.json"
    _snapshot_file(snap, {"prereview": 1})
    assert check_walk_shape.main(_args(m, "--sciety-index", str(snap))) == 1
    assert "absent from the index" in capsys.readouterr().out


def test_count_difference_is_a_note_not_an_issue(tmp_path: Path, capsys):
    m = tmp_path / "manifests"
    _walk(m, "prereview", 1690)
    _run_manifest(m, {"evaluations__prereview": "w01"})
    snap = tmp_path / "index.json"
    _snapshot_file(snap, {"prereview": 1693})
    assert check_walk_shape.main(_args(m, "--sciety-index", str(snap))) == 0
    assert "note: walk accepted 1690 item(s), index carries 1693 docmap(s)" in capsys.readouterr().out


def test_probe_and_full_index_walks_are_not_judged_for_coverage(tmp_path: Path, capsys):
    m = tmp_path / "manifests"
    _walk(m, "", 1725, scope="index__all")
    _walk(m, "", 1725, scope="evaluations__full_index")
    _run_manifest(m, {"index__all": "w01", "evaluations__full_index": "w01"}, INDEX)
    assert check_walk_shape.main(_args(m, "--json")) == 0
    walks = {w["scope"]: w for w in json.loads(capsys.readouterr().out)["walks"]}
    assert walks["index__all"]["index_coverage"] == "" and walks["index__all"]["issues"] == []
    assert walks["evaluations__full_index"]["index_coverage"] == ""


def test_without_any_index_behaviour_is_unchanged(tmp_path: Path, capsys):
    m = _setup(tmp_path)
    assert check_walk_shape.main(_args(m)) == 0
    out = capsys.readouterr().out
    assert "sciety index (rule 6): not consulted" in out
    assert "index=not checked" in out and "sciety index coverage" not in out


def test_missing_or_unreadable_snapshot_is_inconclusive(tmp_path: Path):
    m = _setup(tmp_path)
    assert check_walk_shape.main(_args(m, "--sciety-index", str(tmp_path / "nope.json"))) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert check_walk_shape.main(_args(m, "--sciety-index", str(bad))) == 2
    no_articles = tmp_path / "no_articles.json"
    no_articles.write_text(json.dumps({"items": []}), encoding="utf-8")
    assert check_walk_shape.main(_args(m, "--sciety-index", str(no_articles))) == 2


def test_snapshot_without_group_accounts_is_inconclusive_not_a_pass(tmp_path: Path, capsys):
    m = _setup(tmp_path)
    snap = tmp_path / "foreign.json"
    _snapshot_file(snap, {"x": 2}, account_form=lambda slug: "urn:" + slug)
    assert check_walk_shape.main(_args(m, "--sciety-index", str(snap))) == 2
    out = capsys.readouterr().out
    assert "no sciety.org group accounts" in out and "index=not checked" in out


def test_non_selected_sciety_walk_is_not_judged_for_coverage(tmp_path: Path, capsys):
    m = _setup(tmp_path)
    _walk(m, "biophysics-colab", 32, walk_id="w02")
    _run_manifest(m, {**{f"evaluations__{slug}": "w01" for slug in WALKS}, "evaluations__biophysics-colab": "w02"})
    snap = tmp_path / "index.json"
    _snapshot_file(snap, INDEX)
    assert check_walk_shape.main(_args(m, "--sciety-index", str(snap), "--json")) == 0
    walks = {(w["scope"], w["walk_id"]): w for w in json.loads(capsys.readouterr().out)["walks"]}
    assert walks[("evaluations__biophysics-colab", "w01")]["judged"] is False
    assert walks[("evaluations__biophysics-colab", "w01")]["index_coverage"] == ""
    assert walks[("evaluations__biophysics-colab", "w02")]["issues"] == []
