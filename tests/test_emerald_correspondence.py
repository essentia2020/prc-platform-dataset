"""Documented Emerald correspondence; remaining corpus examples are synthetic."""

import csv
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from src.analyse.build_aggregates import analyse_row, _works_row
from src.common.correspondence import canonical_work_doi, correspondence_index
from src.common.identifiers import IdentifierError
from src.common.interim import read_csv
from src.common.raw_store import RawStore
from src.common.register import load_platforms
from src.common.run_state import RowState, load_row_states
from src.extract import crossref_peer_reviews, crossref_works
from src.extract.crossref_common import inverse_review_targets
from src.extract.selectors import compile_crossref_selector
from src.normalise.clean_and_normalise import build_row_records, work_records
from tests.offline import FixtureTransport, crossref_page, run_context


V1 = "10.12688/emeraldopenres.13140.1"
V2 = "10.35241/emeraldopenres.13140.2"
PRIMARY = "10.1108/eor-03-2023-0005"
BASIS = "version_stem+alias+relation"
REVIEW1 = "10.21956/emeraldopenres.14208.r26506"
REVIEW2 = "10.21956/emeraldopenres.14208.r26414"


def emerald():
    return deepcopy(next(r for r in load_platforms() if r["row_id"] == "emerald_open_research"))


def fixture_items():
    # DOI/date/relation chain confirmed for 13140; labels and review dates are
    # synthetic. No full source response is represented by this fixture.
    first = {"DOI": V1, "type": "journal-article", "title": ["Synthetic paired title"],
             "issued": {"date-parts": [[2019, 6, 7]]},
             "created": {"date-time": "2019-07-04T00:00:00Z"},
             "relation": {
                 "new_version": [{"id-type": "doi", "id": V2, "asserted-by": "object"}],
                 "has-review": [{"id-type": "doi", "id": REVIEW1},
                                {"id-type": "doi", "id": REVIEW2}]}}
    primary = {"DOI": PRIMARY, "type": "journal-article", "title": ["Synthetic paired title"],
               "issued": {"date-parts": [[2019, 12, 9]]},
               "created": {"date-time": "2024-01-17T00:00:00Z"}, "relation": {}}
    reviews = [
        {"DOI": REVIEW1, "type": "peer-review", "issued": {"date-parts": [[2020, 1, 1]]},
         "relation": {"is-review-of": [{"id-type": "doi", "id": V1}]}},
        {"DOI": REVIEW2, "type": "peer-review", "issued": {"date-parts": [[2020, 1, 2]]},
         "relation": {}},
        {"DOI": "10.21956/emeraldopenres.13140.r99999", "type": "peer-review",
         "issued": {"date-parts": [[2020, 1, 3]]}, "relation": {}},
    ]
    return [first, primary], reviews


def extract(tmp_path):
    config, sources, _, logger, roots = run_context(tmp_path)
    row = emerald()
    items, reviews = fixture_items()
    transport = FixtureTransport({
        "issn:2631-3952,type:journal-article": [crossref_page(200, payload={
            "status": "ok", "message": {"items": items, "total-results": 2}})],
        "prefix:10.21956,type:peer-review": [crossref_page(200, payload={
            "status": "ok", "message": {"items": reviews, "total-results": 3}})],
    })
    for module in (crossref_works, crossref_peer_reviews):
        module.run(config, sources, [row], logger, transport=transport, sleeper=lambda _: None, **roots)
    _, states = load_row_states(roots["manifest_root"], config.run_id, [row])
    records = build_row_records(row, states[row["row_id"]], roots["interim_root"])
    return config, row, roots, records, transport, states[row["row_id"]]


def test_triple_retained_counted_once_at_earliest_retrieved_date(tmp_path):
    config, row, roots, records, transport, state = extract(tmp_path)
    works = [r for r in records if r["row_entity_type"] == "work_record"]
    by_id = {r["work_id"]: r for r in works}
    assert len(works) == 2  # alias is evidence, not an invented third source record
    assert by_id["doi:" + V1]["record_flag"] == ""
    assert by_id["doi:" + PRIMARY]["record_flag"] == "later_version"
    assert {r["canonical_work_id"] for r in works} == {"doi:" + PRIMARY}
    assert {r["correspondence_basis"] for r in works} == {BASIS}
    analysis = analyse_row(row, state, records, config.analysis_cutoff_date)
    assert len(analysis.included_works()) == 1
    output = _works_row(analysis.included_works()[0])
    assert output["canonical_work_id"] == "doi:" + PRIMARY
    assert output["counting_record_id"] == V1
    assert output["counting_event_date_raw"] == "2019-06-07"
    assert output["counting_record_created"].startswith("2019-07-04")
    assert output["correspondence_basis"] == BASIS
    assert set(output["contributing_record_ids"].split("; ")) == {V1, PRIMARY}
    interim = read_csv(roots["interim_root"] / "crossref_works__emerald_open_research.csv")
    assert {r["doi"] for r in interim} == {V1, PRIMARY}
    rel = json.loads(next(r for r in interim if r["doi"] == V1)["relation_json"])
    assert rel["new_version"][0]["id"] == V2
    assert rel["new_version"][0]["asserted-by"] == "object"
    assert all("/works/" not in r["url"] for r in transport.requests)  # no alias API lookup


def test_reviews_use_relations_not_stems(tmp_path):
    _, _, roots, records, _, _ = extract(tmp_path)
    evaluations = [r for r in records if r["row_entity_type"] == "evaluation_record"]
    assert {r["review_record_id"] for r in evaluations} == {REVIEW1, REVIEW2}
    relations = [r for r in records if r["row_entity_type"] == "evaluation_relation"]
    assert len(relations) == 2
    assert {r["relation_type"] for r in relations} == {"is-review-of", "has-review"}
    assert {r["reviewed_canonical_work_id"] for r in relations} == {"doi:" + PRIMARY}
    assert {r["correspondence_basis"] for r in relations} == {BASIS}
    unattributed = read_csv(roots["interim_root"] / "crossref_peer_reviews__unattributed__10.21956.csv")
    assert {r["doi"] for r in unattributed} == {"10.21956/emeraldopenres.13140.r99999"}


def test_reflattening_completed_walks_requires_no_new_requests(tmp_path):
    config, row, roots, _, _, _ = extract(tmp_path)
    _, sources, _, logger, _ = run_context(tmp_path)

    def forbidden_transport(*args):
        raise AssertionError("completed walks must be reused without requests")

    # The selector can be widened and completed raw walks re-flattened. Neither
    # the new v1 selection nor inverse has-review evidence requires a new walk.
    for module in (crossref_works, crossref_peer_reviews):
        module.run(config, sources, [row], logger, transport=forbidden_transport,
                   sleeper=lambda _: None, **roots)
    interim = read_csv(roots["interim_root"] / "crossref_works__emerald_open_research.csv")
    assert {r["doi"] for r in interim} == {V1, PRIMARY}


@pytest.mark.parametrize("target", [V1, V2, PRIMARY])
def test_explicit_review_target_maps_to_primary(target):
    sel = compile_crossref_selector(emerald())
    from src.extract.selectors import review_targets
    item = {"DOI": REVIEW1, "type": "peer-review",
            "relation": {"is-review-of": [{"id-type": "doi", "id": target}]}}
    assert sel.claims_review(item, review_targets(item))
    assert canonical_work_doi(emerald(), target) == (PRIMARY, BASIS)


def interim_work(doi, issued, title="Synthetic title"):
    return {"doi": doi, "type": "journal-article", "title": title, "issued": issued,
            "walk_id": "w01", "page": "1"}


def analyse_interim(items):
    row = emerald()
    records = work_records(row, items)
    state = RowState(row["row_id"], "quantified",
                     primary_scopes={"crossref/fixture": "complete"})
    return records, analyse_row(row, state, records, date(2026, 9, 30))


def test_151_synthetic_records_yield_150_works():
    items = [interim_work(V1, "2019-06-07"), interim_work(PRIMARY, "2019-12-09")]
    items += [interim_work(f"10.1108/eor-synthetic-{n}", "2020-05-01") for n in range(149)]
    records, analysis = analyse_interim(items)
    assert len(records) == 151
    assert len(analysis.included_works()) == 150
    assert sum(r["record_flag"] == "later_version" for r in records) == 1


def test_primary_alone_never_gets_an_unretrieved_v1_date():
    records, analysis = analyse_interim([interim_work(PRIMARY, "2019-12-09")])
    assert records[0]["record_flag"] == ""
    assert _works_row(analysis.included_works()[0])["counting_event_date_raw"] == "2019-12-09"


def test_linked_versions_across_years_use_earliest_retrieved_year():
    # Deliberately synthetic dates prove the rule is not fixed to a calendar year.
    records, analysis = analyse_interim([interim_work(PRIMARY, "2020-01-01"),
                                         interim_work(V1, "2019-12-31")])
    assert analysis.included_works()[0].counting_year == 2019
    assert {r["work_id"]: r["record_flag"] for r in records}["doi:" + PRIMARY] == "later_version"


def test_identical_titles_and_different_dates_never_merge_unlinked_primaries():
    records, analysis = analyse_interim([
        interim_work("10.1108/eor-synthetic-a", "2019-06-07"),
        interim_work("10.1108/eor-synthetic-b", "2020-12-09")])
    assert len(analysis.included_works()) == 2
    assert all(r["correspondence_basis"] == "" for r in records)
    assert canonical_work_doi(emerald(), "10.12688/emeraldopenres.13141.1")[0] != PRIMARY


def test_inverse_review_evidence_requires_complete_work_walk(tmp_path):
    config, _, _, _, roots = run_context(tmp_path)
    out = inverse_review_targets(config, [compile_crossref_selector(emerald())],
                                  RawStore(roots["raw_root"]), roots["manifest_root"])
    assert out == {}


@pytest.mark.parametrize("field,value", [
    ("alias_doi", "10.35241/emeraldopenres.13141.2"),
    ("version_stem", "emeraldopenres.99999"),
    ("correspondence_basis", "title"),
    ("evidence_urls", []),
])
def test_invalid_or_title_only_correspondence_is_rejected(field, value):
    row = emerald()
    row["extraction_selector"]["crossref"]["work_correspondences"][0][field] = value
    with pytest.raises(IdentifierError):
        correspondence_index(row)


def test_date_semantics_preset_has_unknown_magnitude_and_run_independent_handling():
    path = Path(__file__).resolve().parents[1] / "data/processed/data_quality_log.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(None not in r for r in rows)
    issue = next(r for r in rows if r["issue_id"] == "DQ-012")
    assert issue["row_id"] == "emerald_open_research" and issue["issue_type"] == "date_semantics"
    assert issue["origin"] == "preset" and issue["status"] == "template"
    assert issue["n_records_affected"] == issue["run_id"] == issue["walk_id"] == ""
    assert "Magnitude: unknown" in issue["effect_on_counts"]
    assert BASIS in issue["handling"]
    assert "run_20261026_01" not in issue["handling"]
