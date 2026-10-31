"""D-058: the Sciety docmaps index lists only groups enabled for docmaps.

The Sciety stage walks the unfiltered index once per run (scope
``index__all``) and records, per group scope, whether the group is present
in that snapshot.  A quantified row whose primary scopes are all Sciety
groups absent from the snapshot is ``source_not_covering``: every cell
``not_observable``, no count, a data-quality row naming the snapshot.  A
group present in the index that yields zero items keeps the D-047 verdict
``selector_no_match``.  Nothing here is ever ``observed_zero``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.interim import read_csv
from src.common.manifest import load_run_manifest, run_manifest_path
from src.common.run_state import RowState, row_states
from src.extract import sciety_evaluations
from src.extract.crossref_common import ExtractionIncomplete, http_settings
from tests.offline import FixtureTransport, crossref_page, make_run_config, run_context, run_full_pipeline

ABSENT_ROWS = ("metaror", "review_commons", "peerref", "the_unjournal")


def _active_cells(outputs, row_id):
    """Coverage-matrix cells of the row inside its register coverage (years before launch are not_applicable)."""
    return [c for c in outputs.table("coverage_matrix") if c["row_id"] == row_id
            and c["observation_status"] != "not_applicable"]


def _dq(outputs):
    return list(read_csv(outputs.processed / "data_quality_log.csv"))


class _IndexDown(FixtureTransport):
    """The unfiltered index fails; every per-group request is served from the fixtures."""

    def __call__(self, url, headers, timeout):
        if url.endswith("/docmaps/v1/index"):
            self.requests.append({"url": url, "headers": dict(headers)})
            return crossref_page(503)
        return super().__call__(url, headers, timeout)


def _stage(tmp_path: Path, transport=None):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    outcomes = sciety_evaluations.run(run_config, sources, platforms, logger, transport=transport or FixtureTransport(),
                                      sleeper=lambda s: None, **roots)
    manifest = load_run_manifest(run_manifest_path(roots["manifest_root"], run_config.run_id))
    return outcomes, manifest, roots, run_config, platforms


# ----------------------------------------------------------------- stage
def test_index_probe_is_recorded_once_per_run_with_group_counts(tmp_path: Path):
    outcomes, manifest, roots, run_config, _ = _stage(tmp_path)
    probe = manifest["scopes"]["sciety/index__all"]
    assert probe["extraction_status"] == "complete" and probe["role"] == "coverage_probe"
    snap = manifest["sciety_index_snapshot"]
    assert snap["scope"] == "index__all" and snap["walk_id"] == probe["selected_walk_id"]
    assert snap["docmaps_total"] == sum(snap["groups"].values()) == 4      # three PREreview-fixture docmaps + one Biophysics Colab
    assert len(snap["page_sha256"]) == snap["pages"] == 1 and snap["page_sha256"][0]
    assert "https://sciety.org/groups/00000000-0000-0000-0000-000000000000" in snap["groups"]   # foreign group listed as served
    by_row = {o.scope.row_id: o for o in outcomes}
    prereview = by_row["prereview"].index_coverage
    assert prereview["status"] == "in_index" and prereview["docmaps_in_index"] == 2 == prereview["docmaps_walked"]
    assert prereview["index_walk_id"] == snap["walk_id"] and prereview["index_retrieved_at"] == snap["retrieved_at"]
    for row_id in ABSENT_ROWS:
        cov = by_row[row_id].index_coverage
        assert cov == {"status": "not_in_index", "docmaps_in_index": 0, "docmaps_walked": 0,
                       "index_walk_id": snap["walk_id"], "index_retrieved_at": snap["retrieved_at"]}
    assert manifest["scopes"]["sciety/evaluations__metaror"]["index_coverage"]["status"] == "not_in_index"
    assert manifest["scopes"]["sciety/evaluations__prereview"]["index_coverage"]["status"] == "in_index"


def test_probe_walk_is_reused_on_a_second_invocation(tmp_path: Path):
    _stage(tmp_path)
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = FixtureTransport()
    sciety_evaluations.run(run_config, sources, platforms, logger, transport=transport, sleeper=lambda s: None, **roots)
    assert transport.requests == []            # every walk, the probe included, reused


def test_failed_probe_leaves_coverage_unverified_and_makes_the_stage_incomplete(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    with pytest.raises(ExtractionIncomplete) as excinfo:
        sciety_evaluations.run(run_config, sources, platforms, logger, transport=_IndexDown(),
                               sleeper=lambda s: None, **roots)
    assert "index__all: failed (coverage of zero-item groups unverified)" in str(excinfo.value)
    assert "blocks" not in str(excinfo.value)                 # no group walk failed
    manifest = load_run_manifest(run_manifest_path(roots["manifest_root"], run_config.run_id))
    assert "sciety_index_snapshot" not in manifest
    assert manifest["scopes"]["sciety/index__all"]["extraction_status"] == "failed"
    entry = manifest["scopes"]["sciety/evaluations__metaror"]
    assert entry["extraction_status"] == "complete"
    assert entry["index_coverage"]["status"] == "unverified" and entry["index_coverage"]["docmaps_in_index"] is None
    assert (roots["interim_root"] / "sciety_evaluations__metaror.csv").exists()
    states = row_states(manifest, platforms)
    assert states["metaror"].extraction_status == "complete" and not states["metaror"].source_not_covering


def test_full_index_mode_uses_the_data_walk_as_snapshot(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    sources["sources"]["sciety"]["retrieval_mode"] = "full_index"
    rows = [r for r in platforms if r["row_id"] in ("prereview", "metaror")]
    transport = FixtureTransport()
    outcomes = sciety_evaluations.run(run_config, sources, rows, logger, transport=transport, sleeper=lambda s: None, **roots)
    assert len(transport.requests) == 1 and "publisheraccount" not in transport.requests[0]["url"]
    manifest = load_run_manifest(run_manifest_path(roots["manifest_root"], run_config.run_id))
    assert manifest["sciety_index_snapshot"]["scope"] == "evaluations__full_index"
    assert "sciety/index__all" not in manifest["scopes"]
    by_row = {o.scope.row_id: o for o in outcomes}
    assert by_row["prereview"].index_coverage["status"] == "in_index"
    assert by_row["prereview"].index_coverage["docmaps_walked"] == 2
    assert by_row["metaror"].index_coverage["status"] == "not_in_index"


# -------------------------------------------------------------- run state
def test_row_state_requires_every_primary_scope_absent():
    def state(primary, coverage):
        return RowState("r", "quantified", primary_scopes=primary, index_coverage=coverage)
    assert state({"sciety/evaluations__x": "complete"}, {"sciety/evaluations__x": "not_in_index"}).source_not_covering
    assert not state({"sciety/evaluations__x": "complete"}, {"sciety/evaluations__x": "in_index"}).source_not_covering
    assert not state({"sciety/evaluations__x": "complete"}, {"sciety/evaluations__x": "unverified"}).source_not_covering
    assert not state({"sciety/evaluations__x": "complete"}, {}).source_not_covering
    # a row with a Crossref primary scope as well is a selector question, never source_not_covering
    assert not state({"sciety/evaluations__x": "complete", "crossref/works__10.1__peer-review": "complete"},
                     {"sciety/evaluations__x": "not_in_index"}).source_not_covering
    assert not state({}, {}).source_not_covering


def test_cross_check_coverage_is_carried_but_never_blocks():
    manifest = {"run_id": "r", "scopes": {
        "sciety/evaluations__elife": {"extraction_status": "complete", "selected_walk_id": "w01",
                                      "index_coverage": {"status": "not_in_index"}}}}
    from src.common.register import load_platforms
    rows = [r for r in load_platforms() if r["row_id"] == "elife_reviewed_preprints"]
    st = row_states(manifest, rows)["elife_reviewed_preprints"]
    assert st.index_coverage == {"sciety/evaluations__elife": "not_in_index"}
    assert not st.source_not_covering          # cross-check scope only; primary scopes are Crossref


# --------------------------------------------------------------- analysis
@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    # biophysics-colab is present in the index (one docmap) but its per-group response is empty:
    # the register's zero there is a selector question (D-047), not a coverage one (D-058)
    transport = FixtureTransport(scripted={"groups%2Fbiophysics-colab": [(200, {}, b'{"articles": []}')]})
    return run_full_pipeline(tmp_path_factory.mktemp("d058"), transport=transport)


def test_absent_groups_are_source_not_covering_never_zero(outputs):
    rows = outputs.analysis_manifest["rows"]
    for row_id in ABSENT_ROWS:
        assert rows[row_id]["source_not_covering"] is True and rows[row_id]["selector_no_match"] is False
        assert rows[row_id]["extraction_status"] == "complete"
        assert set(rows[row_id]["index_coverage"].values()) == {"not_in_index"}
        cells = _active_cells(outputs, row_id)
        assert cells and {c["source_observability_status"] for c in cells} == {"source_not_covering"}
        assert {c["observation_status"] for c in cells} == {"not_observable"}
        assert all("absent from the Sciety docmaps index" in c["note"] for c in cells)
        yearly = [c for c in outputs.table("works_by_row_year") if c["row_id"] == row_id]
        assert yearly and all(c["count"] == "" and c["observation_status"] != "observed_zero" for c in yearly)
        summary = next(r for r in outputs.table("register_summary") if r["row_id"] == row_id)
        assert summary["unique_works_to_cutoff"] == ""


def test_present_group_with_empty_response_stays_selector_no_match(outputs):
    row = outputs.analysis_manifest["rows"]["biophysics_colab"]
    assert row["selector_no_match"] is True and row["source_not_covering"] is False
    assert row["index_coverage"] == {"sciety/evaluations__biophysics-colab": "in_index"}
    cells = _active_cells(outputs, "biophysics_colab")
    assert cells and {c["source_observability_status"] for c in cells} == {"selector_no_match"}


def test_prereview_is_in_index_and_counted(outputs):
    row = outputs.analysis_manifest["rows"]["prereview"]
    assert row["index_coverage"] == {"sciety/evaluations__prereview": "in_index"}
    assert row["source_not_covering"] is False and row["selector_no_match"] is False


def test_data_quality_row_names_the_snapshot(outputs):
    run_id = outputs.run_config.run_id
    dq = [r for r in _dq(outputs)
          if r["issue_type"] == "source_not_covering" and r["run_id"] == run_id]
    rows = outputs.analysis_manifest["rows"]
    # in the fixtures every Sciety-only group except PREreview and Biophysics Colab is absent from the index
    assert {r["row_id"] for r in dq} == {row_id for row_id, r in rows.items() if r["source_not_covering"]}
    assert set(ABSENT_ROWS) <= {r["row_id"] for r in dq}
    assert "prereview" not in {r["row_id"] for r in dq} and "biophysics_colab" not in {r["row_id"] for r in dq}
    for r in dq:
        assert r["origin"] == "run" and r["status"] == "observed" and r["effect_on_counts"] == "no count published for the row"
        assert "sciety_index_snapshot walk w01 (4 docmaps, retrieved 20" in r["evidence"] and "sha256 " in r["evidence"]
        assert "source_observability_status=source_not_covering" in r["handling"] and "D-058" in r["handling"]
    assert not [r for r in _dq(outputs) if r["issue_type"] == "selector_no_match"
                and r["row_id"] in ABSENT_ROWS]


def test_source_not_covering_rows_are_excluded_from_group_cells_not_blocking(outputs):
    """D-061 (amends D-058 for group cells): the row's own cells stay not_observable; the group cell is
    published without the row and names it in ``excluded_rows``."""
    for name in ("unique_works_by_class_year", "unique_works_all_rows_year", "works_by_class_year",
                 "works_by_configuration_year", "unique_works_by_configuration_year"):
        rows = outputs.table(name)
        assert not [r for r in rows if "source_not_covering" in r["blocking_rows"]], name
        excluded = [r for r in rows if r["excluded_rows"]]
        assert excluded, name
        for r in excluded:
            assert {e.split(":")[1] for e in r["excluded_rows"].split("; ")} == {"source_not_covering"}
    # community_initiated 2024: the absent Sciety-only groups are excluded, the cell publishes with the members
    # the index does carry (prereview, qeios_external_works)
    cell = outputs.cell("works_by_class_year", initiation_class="community_initiated", year=2024)
    assert cell["count"] == "3" and cell["blocking_rows"] == ""
    for row_id in ("prelights", "arcadia_science", "asapbio_crowd_review", "rapid_reviews_infectious_diseases"):
        assert f"{row_id}:source_not_covering" in cell["excluded_rows"]
    assert cell["coverage"] == "partial_coverage"
    own = outputs.cell("works_by_row_year", row_id="prelights", year=2024)
    assert own["count"] == "" and own["source_observability_status"] == "source_not_covering"
    assert own["observation_status"] == "not_observable"
    # a present group with an empty response (biophysics_colab, D-047) still blanks its group cells
    blocked = [r for r in outputs.table("works_by_class_year")
               if r["initiation_class"] == "mixed" and "biophysics_colab:selector_no_match" in r["blocking_rows"]]
    assert blocked and all(r["count"] == "" for r in blocked)
    assert all("the_unjournal:source_not_covering" in r["excluded_rows"] for r in blocked if int(r["year"]) >= 2023)


# ----------------------------------------------------------- http settings
def test_per_source_http_block_sits_between_defaults_and_run_overrides():
    sources = {"http_defaults": {"timeout_seconds": 60, "accept": "application/json"},
               "sources": {"sciety": {"http": {"timeout_seconds": 300}}, "crossref": {}}}
    cfg = make_run_config()
    assert http_settings(cfg, sources, "sciety")["timeout_seconds"] == 300
    assert http_settings(cfg, sources, "crossref")["timeout_seconds"] == 60
    assert http_settings(cfg, sources)["timeout_seconds"] == 60
    cfg.extra["http"] = {"timeout_seconds": 15}
    assert http_settings(cfg, sources, "sciety")["timeout_seconds"] == 15


def test_sciety_client_reads_the_per_source_timeout(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    sources["sources"]["sciety"]["http"] = {"timeout_seconds": 300}
    client = sciety_evaluations.build_client(run_config, sources, transport=FixtureTransport(), sleeper=lambda s: None)
    assert client.timeout == 300
