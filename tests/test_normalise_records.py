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


# ---------------------------------------------------------------- D-067: two F1000Research DOI forms
def _f1000_row():
    from src.common import register
    return {r["row_id"]: r for r in register.load_platforms()}["f1000research"]


@pytest.mark.parametrize("doi, stem", [
    ("10.12688/f1000research.2-73.v1", "10.12688/f1000research.2-73"),
    ("10.12688/f1000research.1-10.v2", "10.12688/f1000research.1-10"),
    ("10.12688/f1000research.15931.1", "10.12688/f1000research.15931"),
    ("10.12688/f1000research.15931.2", "10.12688/f1000research.15931"),
])
def test_f1000research_canonical_stem_for_both_doi_forms(doi, stem):
    from src.common.identifiers import canonical_doi
    row = _f1000_row()
    assert canonical_doi(doi, row["doi_version_pattern"]) == stem


@pytest.mark.parametrize("doi", [
    "10.12688/f1000research.2-73.v1", "10.12688/f1000research.1-10.v2", "10.12688/f1000research.15931.1",
])
def test_f1000research_selector_accepts_both_doi_forms(doi):
    import re
    row = _f1000_row()
    assert re.match(row["extraction_selector"]["crossref"]["doi_regex"], doi)
    assert re.match(row["doi_pattern"], doi)


@pytest.mark.parametrize("doi", [
    "10.12688/f1000research.15931",            # version-free stem is not a record DOI
    "10.12688/f1000research.2-73.1",           # mixed forms are not accepted
    "10.12688/f1000research.15931.v1",
    "10.12688/wellcomeopenres.15931.1",        # other F1000-hosted venues keep their own rows
])
def test_f1000research_selector_rejects_other_forms(doi):
    import re
    row = _f1000_row()
    assert not re.match(row["extraction_selector"]["crossref"]["doi_regex"], doi)


# ------------------------------------------------------------------ D-074
def test_crossref_relation_lines_are_unique_per_review_and_target():
    """One ``evaluation_relation`` line per (source, review record, reviewed work) in the Crossref branch."""
    from src.normalise.clean_and_normalise import review_records

    row = {"row_id": "x", "doi_version_pattern": None, "extraction_selector": {"crossref": {}}}
    line = {"doi": "10.21956/test.1.r1", "type": "peer-review", "issued": "2024-03-01",
            "target_id_raw": "10.12688/test.1.1", "target_id_type": "doi", "target_relation_type": "is-review-of"}
    recs = review_records(row, [line, dict(line, page="2"), dict(line, target_id_raw="10.12688/test.2.1")], set())
    rels = [(r["source"], r["review_record_id"], r["reviewed_work_id"]) for r in recs
            if r["row_entity_type"] == "evaluation_relation"]
    assert len(rels) == 2 and len(set(rels)) == 2
    assert sum(1 for r in recs if r["row_entity_type"] == "evaluation_record") == 1


def test_relation_key_is_unique_in_every_records_file(pipeline_outputs):
    """Offline fixture: no records file carries a duplicate (source, review_record_id, reviewed_work_id)."""
    out = pipeline_outputs
    checked = 0
    for path in sorted(out.processed.glob("records_*.csv")):
        row_id = path.stem[len("records_"):]
        rels = [(r["source"], r["review_record_id"], r["reviewed_work_id"]) for r in out.records(row_id)
                if r["row_entity_type"] == "evaluation_relation"]
        assert len(rels) == len(set(rels)), row_id
        checked += len(rels)
    assert checked > 0
