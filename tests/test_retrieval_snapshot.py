"""Snapshot provenance of the analysis tables (D-066, note of 2026-11-05).

The snapshot printed in every table header is the latest completion time of
the selected Crossref/Sciety walks, not the last write to the run manifest.
The OpenAlex diagnostics stage records its own time in its own field and
leaves ``retrieval_finished_at`` alone, so running it after ``analyse`` and
re-running ``analyse`` reproduces the tables byte for byte.
"""

import json

from src.analyse import build_aggregates
from src.common.manifest import (load_run_manifest, retrieval_snapshot, run_manifest_path,
                                 update_run_manifest_field, write_run_manifest)
from src.extract import openalex_diagnostics as oa
from tests.offline import run_full_pipeline
from tests.test_openalex_diagnostics import KEY, OpenAlexTransport


def _manifest(**extra):
    payload = {
        "run_id": "run_x", "retrieval_started_at": "2026-11-02T08:38:40Z",
        "retrieval_finished_at": "2026-11-05T11:51:33Z",
        "scopes": {
            "crossref/works__a": {"source": "crossref", "completed_at": "2026-11-02T09:10:00Z"},
            "crossref/works__b": {"source": "crossref", "completed_at": "2026-11-05T09:55:03Z",
                                  "recorded_at": "2026-11-05T10:42:10Z"},
            "crossref/works__c": {"source": "crossref", "completed_at": None, "extraction_status": "failed"},
            "sciety/evaluations__g": {"source": "sciety", "completed_at": "2026-11-02T12:08:34Z"},
        },
        "sciety_index_snapshot": {"walk_id": "w01", "retrieved_at": "2026-11-02T12:06:09Z"},
        "openalex_diagnostics": {"role": "diagnostic", "recorded_at": "2026-11-05T11:51:30Z"},
    }
    payload.update(extra)
    return payload


def test_snapshot_is_the_latest_selected_walk_not_the_last_manifest_write():
    assert retrieval_snapshot(_manifest()) == "2026-11-05T09:55:03Z"
    # the index snapshot counts as a retrieval (D-058); diagnostics and later writes do not
    assert retrieval_snapshot(_manifest(sciety_index_snapshot={"retrieved_at": "2026-11-06T00:00:00Z"})) == \
        "2026-11-06T00:00:00Z"
    later = _manifest(retrieval_finished_at="2026-11-07T00:00:00Z",
                      openalex_diagnostics={"recorded_at": "2026-11-07T00:00:00Z"})
    assert retrieval_snapshot(later) == "2026-11-05T09:55:03Z"
    assert retrieval_snapshot({"run_id": "run_x", "scopes": {}}) == ""


def test_diagnostic_field_write_leaves_the_retrieval_window(tmp_path):
    path = run_manifest_path(tmp_path, "run_x")
    write_run_manifest(path, _manifest())
    update_run_manifest_field(path, run_id="run_x", key="openalex_diagnostics", value={"recorded_at": "later"},
                              retrieval=False, now=lambda: "2026-11-09T00:00:00Z")
    payload = load_run_manifest(path)
    assert payload["retrieval_finished_at"] == "2026-11-05T11:51:33Z"
    assert payload["openalex_diagnostics"] == {"recorded_at": "later"}
    update_run_manifest_field(path, run_id="run_x", key="sciety_index_snapshot", value={"retrieved_at": "x"},
                              now=lambda: "2026-11-09T00:00:00Z")
    assert load_run_manifest(path)["retrieval_finished_at"] == "2026-11-09T00:00:00Z"


def test_diagnostics_after_analyse_leave_the_tables_unchanged(tmp_path):
    out = run_full_pipeline(tmp_path, with_figures=False)
    manifest_file = run_manifest_path(out.roots["manifest_root"], out.run_config.run_id)
    # An offline run finishes within one second, so the last manifest write and the
    # last walk coincide; move the write marker into the past so that a stage which
    # advanced it would be visible whatever the clock does.
    backdated = load_run_manifest(manifest_file)
    backdated["retrieval_finished_at"] = "2026-01-01T00:00:00Z"
    write_run_manifest(manifest_file, backdated)
    from src.common.config import load_sources_config
    from tests.offline import JsonlLogger
    sources = load_sources_config()
    sources["sources"]["openalex"]["source_ids"] = {}
    logger = JsonlLogger(out.run_config.run_id, log_dir=tmp_path / "logs")
    build_aggregates.run(out.run_config, sources, out.platforms, logger, processed_root=out.processed,
                         manifest_root=out.roots["manifest_root"], tables_root=out.tables)
    before_manifest = load_run_manifest(manifest_file)
    tables = sorted(out.tables.glob("*"))
    before = {p.name: p.read_bytes() for p in tables}
    header = [line for line in (out.tables / "register_summary.md").read_text(encoding="utf-8").splitlines()
              if line.startswith("Snapshot:")]
    assert header == [f"Snapshot: last selected Crossref/Sciety walk completed "
                      f"{retrieval_snapshot(before_manifest)}."]
    assert retrieval_snapshot(before_manifest) != ""
    assert retrieval_snapshot(before_manifest) != "2026-01-01T00:00:00Z"

    oa.run(out.run_config, sources, out.platforms, logger, transport=OpenAlexTransport(), sleeper=lambda _: None,
           api_key=KEY, processed_root=out.processed, manifest_root=out.roots["manifest_root"],
           raw_root=out.roots["raw_root"])
    after_manifest = load_run_manifest(manifest_file)
    assert after_manifest["openalex_diagnostics"]["recorded_at"]
    assert after_manifest["retrieval_finished_at"] == "2026-01-01T00:00:00Z"
    assert retrieval_snapshot(after_manifest) == retrieval_snapshot(before_manifest)

    build_aggregates.run(out.run_config, sources, out.platforms, logger, processed_root=out.processed,
                         manifest_root=out.roots["manifest_root"], tables_root=out.tables)
    after = {p.name: p.read_bytes() for p in sorted(out.tables.glob("*"))}
    assert after == before
