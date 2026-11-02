"""Stage 4: record-level layer (§8.5 identifiers, §8.6 evaluation identity, §9.6)."""

from __future__ import annotations

import pytest

from src.common.eligibility import unresolved_relations
from src.normalise.clean_and_normalise import RECORD_COLUMNS, RECORD_FLAGS, NormalisationError, build_row_records
from src.common.run_state import RowState


def _by(rows, **where):
    return [r for r in rows if all(r.get(k) == v for k, v in where.items())]


def test_record_columns_follow_the_dictionary(pipeline_outputs):
    rows = pipeline_outputs.records("qeios_hosted_works")
    assert list(rows[0].keys()) == RECORD_COLUMNS
    assert {r["row_entity_type"] for r in rows} == {"work_record", "evaluation_record", "evaluation_relation"}
    assert all(r["record_flag"] in RECORD_FLAGS for r in rows)


def test_work_id_keeps_version_and_canonical_strips_it(pipeline_outputs):
    rows = pipeline_outputs.records("qeios_hosted_works")
    versioned = _by(rows, row_entity_type="work_record", work_id="doi:10.32388/bbbb22.2")
    assert versioned and versioned[0]["canonical_work_id"] == "doi:10.32388/bbbb22"
    assert versioned[0]["work_doi"] == "10.32388/bbbb22"
    # a relation to a versioned DOI resolves to the same canonical work (boundary test 9)
    rel = _by(rows, row_entity_type="evaluation_relation", review_record_id="10.32388/bbbb22.r1")
    assert rel[0]["reviewed_work_id"] == "doi:10.32388/bbbb22.2"
    assert rel[0]["reviewed_canonical_work_id"] == "doi:10.32388/bbbb22"
    assert rel[0]["reviewed_work_doi"] == "10.32388/bbbb22"


def test_every_relation_has_its_parent_evaluation_record(pipeline_outputs):
    for row_id in ("qeios_hosted_works", "qeios_external_works", "prereview", "f1000research"):
        rows = pipeline_outputs.records(row_id)
        assert unresolved_relations(rows) == []
        for rel in _by(rows, row_entity_type="evaluation_relation"):
            assert rel["canonical_evaluation_id"], rel["review_record_id"]


def test_url_target_uses_url_identifier(pipeline_outputs):
    rows = pipeline_outputs.records("qeios_external_works")
    url_rel = [r for r in _by(rows, row_entity_type="evaluation_relation") if r["reviewed_work_id"].startswith("url:")]
    assert url_rel and url_rel[0]["reviewed_work_doi"] == "" and url_rel[0]["record_flag"] == ""
    assert "example.org" in url_rel[0]["reviewed_work_id"]


def test_withdrawn_title_is_flagged_not_dropped(pipeline_outputs):
    rows = pipeline_outputs.records("qeios_hosted_works")
    withdrawn = _by(rows, row_entity_type="work_record", record_flag="withdrawn")
    assert [r["work_id"] for r in withdrawn] == ["doi:10.32388/cccc33"]


def test_dates_are_kept_at_source_precision(pipeline_outputs):
    rows = pipeline_outputs.records("qeios_hosted_works")
    by_id = {r["work_id"]: r for r in _by(rows, row_entity_type="work_record")}
    assert by_id["doi:10.32388/dddd44"]["event_date_precision"] == "year"
    assert by_id["doi:10.32388/dddd44"]["event_interval_start"] == "2024-01-01"
    assert by_id["doi:10.32388/dddd44"]["event_interval_end"] == "2024-12-31"
    assert by_id["doi:10.32388/bbbb22.2"]["event_date_precision"] == "month"
    assert by_id["doi:10.32388/aaaa11"]["event_date_precision"] == "day"


def test_sciety_evaluation_identity_is_not_the_url(pipeline_outputs):
    rows = pipeline_outputs.records("prereview")
    evals = _by(rows, row_entity_type="evaluation_record")
    statuses = {r["source_evaluation_id"]: r["evaluation_identity_status"] for r in evals}
    assert "doi:10.5281/zenodo.0000001" in {r["canonical_evaluation_id"] for r in evals}
    assert "doi_confirmed" in statuses.values() and "source_only" in statuses.values()
    assert all(r["source_container_id"].startswith("https://sciety.org/docmaps") or r["source_container_id"]
               for r in evals)
    for r in evals:
        assert not r["canonical_evaluation_id"].startswith("url:")
        assert r["evaluation_url"] == "" or r["evaluation_url"] != r["canonical_evaluation_id"]
    # two evaluations within one docmap stay distinct
    docmaps = {}
    for r in evals:
        docmaps.setdefault(r["source_container_id"], set()).add(r["canonical_evaluation_id"])
    assert max(len(v) for v in docmaps.values()) >= 2


def test_copernicus_attribution_is_carried_to_records(pipeline_outputs):
    rows = pipeline_outputs.records("copernicus_interactive_public_peer_review")
    works = {r["work_id"]: r for r in _by(rows, row_entity_type="work_record")}
    assert works["doi:10.5194/egusphere-2025-78"]["exclusion_reason"] == "no_journal_attribution"
    assert works["doi:10.5194/egusphere-2025-78"]["attribution_basis"] == ""
    assert works["doi:10.5194/egusphere-2025-77"]["exclusion_reason"] == ""
    assert works["doi:10.5194/egusphere-2025-77"]["attribution_basis"] != ""
    assert "doi_pattern" in works["doi:10.5194/acpd-15-1-2015"]["attribution_basis"]
    # discussion papers deposited as journal-article are postings, not final articles
    assert {r["event_kind"] for r in works.values()} == {"posting"}


def test_blocked_rows_get_no_records_file(blocked_pipeline_outputs):
    out = blocked_pipeline_outputs
    assert out.extraction_error is not None
    for row_id in ("f1000research", "gates_open_research", "wellcome_open_research"):
        assert not (out.processed / f"records_{row_id}.csv").exists()
    assert (out.processed / "records_qeios_hosted_works.csv").exists()


def test_unknown_flag_is_a_hard_failure(tmp_path, monkeypatch):
    import src.normalise.clean_and_normalise as mod
    row = {"row_id": "x", "extraction_selector": {"crossref": {}}, "counting_event": "first_public_posting"}
    state = RowState(row_id="x", register_status="quantified", primary_scopes={"crossref/works__10.1__posted-content": "complete"})
    (tmp_path / "crossref_works__x.csv").write_text("")
    monkeypatch.setattr(mod, "work_records", lambda row, rows, pairs=None: [dict.fromkeys(RECORD_COLUMNS, "") | {
        "row_id": "x", "row_entity_type": "work_record", "source": "crossref", "record_flag": "bogus"}])
    with pytest.raises(NormalisationError):
        build_row_records(row, state, tmp_path)
