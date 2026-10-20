"""Row technical state from the run manifest (§9.4, §9.7)."""

from src.common.run_state import RowState, row_scopes, row_states


def _manifest(**scopes):
    return {"scopes": {k: {"extraction_status": v, "selected_walk_id": "w1" if v == "complete" else None}
                       for k, v in scopes.items()}}


def test_cross_check_scopes_never_block(pipeline_outputs):
    rows = {str(p["row_id"]): p for p in pipeline_outputs.platforms}
    primary, cross = row_scopes(rows["elife_reviewed_preprints"])
    assert primary and all(k.startswith("crossref/") for k in primary)
    assert cross and all(k.startswith("sciety/") for k in cross)
    manifest = _manifest(**{k: "complete" for k in primary}, **{k: "incomplete" for k in cross})
    state = row_states(manifest, [rows["elife_reviewed_preprints"]])["elife_reviewed_preprints"]
    assert state.extraction_status == "complete" and state.cross_check_complete is False


def test_missing_scope_counts_as_incomplete():
    state = RowState("r", "quantified", primary_scopes={"crossref/a": "complete", "crossref/b": "not_run"})
    assert state.extraction_status == "incomplete" and state.blocking_scopes == ["crossref/b"]
    assert RowState("r", "quantified", primary_scopes={"crossref/a": "failed"}).extraction_status == "failed"
    assert RowState("r", "quantified", primary_scopes={"crossref/a": "failed", "crossref/b": "incomplete"}
                    ).extraction_status == "incomplete"
    assert RowState("r", "register_only").extraction_status == "incomplete" and not RowState("r", "x").primary_scopes


def test_both_source_rows_depend_on_every_primary_scope(pipeline_outputs):
    rows = {str(p["row_id"]): p for p in pipeline_outputs.platforms}
    primary, cross = row_scopes(rows["pci_recommendations"])
    assert any(k.startswith("crossref/") for k in primary)
    pending, _ = row_scopes(rows["verixiv"])
    assert pending == []      # pending selector: no scope, no count
