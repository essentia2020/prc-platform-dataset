"""§8.7/§8.9: the binding publication decision is derived from the configuration and is never a signal."""

from src.analyse.build_aggregates import RECOGNITION_SIGNALS, requires_evaluation
from src.common.eligibility import binding_decision


def test_binding_decision_matches_configuration_in_evidence_table(pipeline_outputs):
    out = pipeline_outputs
    for r in out.table("evidence_features_by_platform"):
        expected = binding_decision(r["prc_configuration"], r["provisional"] == "true")
        assert r["binding_publication_decision"] == ("" if expected is None else ("true" if expected else "false"))
        assert "binding_publication_decision" not in RECOGNITION_SIGNALS
        for signal in RECOGNITION_SIGNALS:
            assert r[signal] in ("true", "false", "unknown", ""), (r["row_id"], signal, r[signal])


def test_register_event_map_is_read_from_the_register(pipeline_outputs):
    rows = {str(p["row_id"]): p for p in pipeline_outputs.platforms}
    needs = {rid for rid, p in rows.items() if requires_evaluation(p)}
    # D-036: pinned set — any change to the derived set, additions included, must fail here
    assert needs == {"qeios_hosted_works", "verixiv"}
    assert len(needs) == 2
    assert rows["elife_reviewed_preprints"]["counting_event"] == "first_public_posting"
    assert not requires_evaluation(rows["elife_reviewed_preprints"])
    for w in pipeline_outputs.works():
        assert w["counting_event"] == rows[w["row_id"]]["counting_event"] or w["included"] == "false"


def test_event_groups_are_kept_separate(pipeline_outputs):
    works = {w["canonical_work_id"]: w for w in pipeline_outputs.works("qeios_hosted_works")}
    w = works["doi:10.32388/bbbb22"]
    assert w["included"] == "true"
    assert w["posting_event_date_raw"] == "2025-02"
    assert w["eligibility_review_event_date_raw"] == "2025-03-01"
    assert w["counting_event_date_raw"] == w["posting_event_date_raw"]          # counting = first posting
    assert w["counting_record_id"] == "10.32388/bbbb22.2"
    assert w["eligibility_review_record_id"] == "doi:10.32388/bbbb22.r1"
    assert w["counting_year"] == "2025" and w["n_evaluation_records"] == "1"


def test_copernicus_fallback_applies_only_to_a_complete_run(pipeline_outputs):
    from src.analyse.build_aggregates import effective_register_status
    row = next(p for p in pipeline_outputs.platforms if p["row_id"] == "copernicus_interactive_public_peer_review")
    fallback = {"attribution": {row["row_id"]: {"effective_register_status": "register_only"}}}
    assert effective_register_status(row, fallback, complete=True) == "register_only"
    assert effective_register_status(row, fallback, complete=False) == "quantified"
    assert effective_register_status(row, {}, complete=True) == "quantified"
    # the fixture run observed signals, so the row stays quantified
    assert pipeline_outputs.cell("register_summary", row_id=row["row_id"])["effective_register_status"] == "quantified"
