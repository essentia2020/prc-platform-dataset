"""tools/check_walk_shape.py: the walk-shape rules as a maintainer CLI.

The CLI reads ``data/manifests/<run_id>`` (rules 1-4) and the local raw store
(rule 5, gzip-compressed pages as the store writes them).  It judges only
complete walks — by default the walk the run manifest selected per scope —
exits 1 on a shape issue, 2 when the check is inconclusive, 0 otherwise, and
writes nothing.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from src.common.manifest import PageEntry, WalkManifestWriter, write_run_manifest
from tools import check_walk_shape

RUN = "run_test_01"
SCOPE = "works__10.1__journal-article"
ROWS = 2


def _store_page(raw_root: Path, walk_id: str, page: int, dois: list[str]) -> tuple[str, str]:
    rel = f"crossref/{SCOPE}/{RUN}/{walk_id}/page_{page}/attempt_1.response.json.gz"
    target = raw_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"message": {"items": [{"DOI": d} for d in dois], "total-results": 0}}).encode("utf-8")
    with target.open("wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0) as gz:
            gz.write(body)
    return rel, hashlib.sha256(target.read_bytes()).hexdigest()


def _write_walk(manifest_root: Path, raw_root: Path, walk_id: str, pages: list[list[str]],
                first_total: int, state: str = "complete", store: bool = True) -> None:
    path = manifest_root / RUN / f"crossref__{SCOPE}__{walk_id}.manifest.jsonl"
    writer = WalkManifestWriter(path, RUN, "crossref", SCOPE, walk_id, now=lambda: "2026-10-27T00:00:00Z")
    cursors = ["*"] + [f"c{i}" for i in range(2, len(pages) + 2)]
    items = 0
    for n, dois in enumerate(pages, start=1):
        rel, digest = (_store_page(raw_root, walk_id, n, dois) if store
                       else (f"crossref/{SCOPE}/{RUN}/{walk_id}/page_{n}/attempt_1.response.json.gz", ""))
        writer.accept_page(PageEntry(page=n, accepted_attempt=1, response_path=rel, sha256=digest, bytes=1,
                                     http_status=200, cursor_in=cursors[n - 1], cursor_out=cursors[n],
                                     items_in_page=len(dois), accepted_at_utc="2026-10-27T00:00:00Z"))
        items += len(dois)
    writer.close(state, "test", pages_accepted=len(pages), items_total=items,
                 completion={"first_page_total_results": first_total, "accepted_items_total": items,
                             "total_delta": items - first_total, "terminal_evidence": "empty_page"})


def _run_manifest(manifest_root: Path, selected: str) -> None:
    write_run_manifest(manifest_root / RUN / f"{RUN}.json",
                       {"run_id": RUN, "scopes": {f"crossref/{SCOPE}": {"selected_walk_id": selected}}})


def _args(tmp_path: Path, *extra: str) -> list[str]:
    return ["--run", RUN, "--manifest-root", str(tmp_path / "manifests"), "--raw-root", str(tmp_path / "raw"),
            "--rows", str(ROWS), *extra]


def test_consistent_walk_exits_zero_and_reads_gzip_pages(tmp_path: Path, capsys):
    m, r = tmp_path / "manifests", tmp_path / "raw"
    _write_walk(m, r, "w01", [["10.1/a", "10.1/b"], ["10.1/c"], []], 3)
    _run_manifest(m, "w01")
    assert check_walk_shape.main(_args(tmp_path, "--json", "--verify-digests")) == 0
    payload = json.loads(capsys.readouterr().out)
    walk = payload["walks"][0]
    assert walk["judged"] and walk["selected"] and walk["issues"] == [] and walk["digest_problems"] == []
    assert walk["non_empty_pages"] == 2 and walk["expected_non_empty_pages"] == 2 and walk["empty_pages"] == 1


def test_duplicate_record_across_pages_exits_one(tmp_path: Path, capsys):
    m, r = tmp_path / "manifests", tmp_path / "raw"
    # the manifest arithmetic is clean (4 items, 2 full pages); only the stored pages show the re-served record
    _write_walk(m, r, "w01", [["10.1/a", "10.1/b"], ["10.1/b", "10.1/c"]], 4)
    _run_manifest(m, "w01")
    assert check_walk_shape.main(_args(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "1 record(s) accepted on more than one page" in out
    # without the raw store the same walk passes rules 1-4
    assert check_walk_shape.main(_args(tmp_path, "--no-raw")) == 0


def test_missing_raw_pages_are_inconclusive_not_passed(tmp_path: Path, capsys):
    m, r = tmp_path / "manifests", tmp_path / "raw"
    r.mkdir()
    _write_walk(m, r, "w01", [["10.1/a", "10.1/b"], []], 2, store=False)
    _run_manifest(m, "w01")
    assert check_walk_shape.main(_args(tmp_path)) == 2
    assert "inconclusive" in capsys.readouterr().out


def test_repeated_cursor_is_an_issue_even_with_zero_delta(tmp_path: Path, capsys):
    m, r = tmp_path / "manifests", tmp_path / "raw"
    path = m / RUN / f"crossref__{SCOPE}__w01.manifest.jsonl"
    writer = WalkManifestWriter(path, RUN, "crossref", SCOPE, "w01", now=lambda: "2026-10-27T00:00:00Z")
    seq = [("*", "c2", 2), ("c2", "c3", 2), ("*", "c2", 2), ("c2", "c3", 2), ("c3", "c4", 1)]
    for n, (cin, cout, items) in enumerate(seq, start=1):
        writer.accept_page(PageEntry(page=n, accepted_attempt=1, response_path=f"p{n}.json.gz", sha256="", bytes=1,
                                     http_status=200, cursor_in=cin, cursor_out=cout, items_in_page=items,
                                     accepted_at_utc=""))
    writer.close("complete", "test", 5, 9, {"first_page_total_results": 9, "total_delta": 0})
    _run_manifest(m, "w01")
    assert check_walk_shape.main(_args(tmp_path, "--no-raw")) == 1
    assert "cursor_in repeated" in capsys.readouterr().out


def test_only_the_selected_walk_is_judged_unless_all_walks(tmp_path: Path, capsys):
    m, r = tmp_path / "manifests", tmp_path / "raw"
    _write_walk(m, r, "w01", [["10.1/a", "10.1/b"], ["10.1/c", "10.1/d"], ["10.1/e"]], 5, state="failed")
    _write_walk(m, r, "w02", [["10.1/a", "10.1/b"], ["10.1/c"], []], 3)
    _write_walk(m, r, "w03", [["10.1/a", "10.1/b"], ["10.1/b", "10.1/c"]], 4)   # complete, duplicate record
    _run_manifest(m, "w02")
    assert check_walk_shape.main(_args(tmp_path, "--json")) == 0
    walks = {w["walk_id"]: w for w in json.loads(capsys.readouterr().out)["walks"]}
    assert walks["w01"]["judged"] is False and walks["w03"]["judged"] is False and walks["w02"]["judged"] is True
    assert check_walk_shape.main(_args(tmp_path, "--all-walks", "--json")) == 1
    walks = {w["walk_id"]: w for w in json.loads(capsys.readouterr().out)["walks"]}
    assert walks["w01"]["judged"] is False        # failed walks are never judged
    assert walks["w03"]["judged"] is True and walks["w03"]["issues"]


def test_missing_run_folder_is_inconclusive(tmp_path: Path, capsys):
    (tmp_path / "raw").mkdir()
    assert check_walk_shape.main(_args(tmp_path)) == 2
    assert "no manifest folder" in capsys.readouterr().out


def test_scope_filter_and_default_rows_from_config(tmp_path: Path, capsys):
    m, r = tmp_path / "manifests", tmp_path / "raw"
    _write_walk(m, r, "w01", [["10.1/a"], []], 1)
    _run_manifest(m, "w01")
    args = ["--run", RUN, "--manifest-root", str(m), "--no-raw", "--scope", "works__10.9__peer-review"]
    assert check_walk_shape.main(args) == 2            # nothing matched: inconclusive, not a pass
    assert "no walk manifests" in capsys.readouterr().out
    args = ["--run", RUN, "--manifest-root", str(m), "--no-raw", "--scope", SCOPE, "--json"]
    assert check_walk_shape.main(args) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 1000
