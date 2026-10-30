"""D-032 through D-035: attribution, scheduling, group integrity and completion."""

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from src.common.aggregates import cell_for
from src.common.config import load_sources_config
from src.common.http import PoliteClient
from src.common.interim import read_csv
from src.common.manifest import list_walks
from src.common.raw_store import RawStore
from src.common.register import load_platforms, load_excluded
from src.common.walk import CursorWalker, WalkError
from src.extract.crossref_common import parse_crossref_page, url_builder
from src.extract import crossref_works, crossref_peer_reviews, sciety_evaluations
from src.extract.selectors import compile_crossref_selector, CrossrefScope
from src.normalise.sciety_integrity import PublisherAccountMismatch
from tests.offline import FixtureTransport, run_context, make_run_config, SCIETY


def page(n, total, nxt=None):
    return {"status": "ok", "message": {"items": [{}] * n, "total-results": total,
                                        "next-cursor": nxt}}


def walk_pages(tmp_path, payloads, tolerance=0, reason=""):
    responses = iter(payloads)
    client = PoliteClient(user_agent="offline", min_interval_seconds=0,
                          transport=lambda *args: (200, {}, json.dumps(next(responses)).encode()),
                          sleeper=lambda _: None)
    walker = CursorWalker(client=client, store=RawStore(tmp_path / "raw"),
                          manifest_root=tmp_path / "manifests", run_id="test", source="crossref",
                          scope="completion", total_tolerance=tolerance, tolerance_reason=reason)
    return walker.run(build_url=lambda c: f"https://example.invalid/works?rows=3&cursor={c}",
                      parse_page=parse_crossref_page, initial_cursor="*")


@pytest.mark.parametrize("payloads,state", [
    ([page(2, 2)], "complete"),
    ([page(3, 3, "next"), page(0, 3)], "complete"),
    ([page(3, 5, "next"), page(2, 5)], "complete"),
    ([page(0, 0)], "complete"),
    ([page(0, 1)], "failed"),
    ([page(2, 3)], "failed"),
    ([page(3, 3)], "complete"),  # absent cursor plus matching total
    ([page(3, 4)], "failed"),  # absent cursor cannot override the total check
    ([page(3, 3, "next"), page(1, 4)], "failed"),  # total drift from first page
    ([page(3, 7, "next"), page(0, 7)], "failed"),
    ([page(1, None)], "failed"),
])
def test_crossref_completion_requires_terminal_evidence_and_total(tmp_path, payloads, state):
    walk = walk_pages(tmp_path, payloads)
    assert walk.state == state
    assert walk.completion["first_page_total_results"] == payloads[0]["message"]["total-results"]
    if state == "complete":
        assert walk.completion["accepted_items_total"] == payloads[0]["message"]["total-results"]
        assert walk.completion["terminal_evidence"] in ("no_next_cursor", "empty_page")


def test_missing_cursor_is_manifest_anomaly_even_on_short_page(tmp_path):
    walk = walk_pages(tmp_path, [page(2, 2)])
    assert walk.state == "complete"
    assert [a["code"] for a in walk.anomalies] == ["missing_next_cursor", "short_page"]


def test_tolerance_is_explicit_and_cannot_override_empty_first_page(tmp_path):
    with pytest.raises(WalkError, match="reason"):
        walk_pages(tmp_path / "invalid", [page(2, 3)], tolerance=1)
    walk = walk_pages(tmp_path / "valid", [page(2, 3)], tolerance=1, reason="documented index drift")
    assert walk.state == "complete"
    assert walk.completion["total_tolerance"] == 1
    assert walk.completion["tolerance_reason"] == "documented index drift"
    assert walk.completion["total_delta"] == -1
    assert walk_pages(tmp_path / "empty", [page(0, 1)], 1, "documented index drift").state == "failed"


def test_crossref_config_has_no_sort_with_cursor():
    sources = load_sources_config()
    config = sources["sources"]["crossref"]
    assert config["pagination"]["mode"] == "cursor"
    assert "sort" not in config["pagination"]
    for template in config["query_templates"].values():
        query = parse_qs(urlsplit(template).query)
        if "cursor" in query:
            assert "sort" not in query
    changed = deepcopy(sources)
    changed["sources"]["crossref"]["query_templates"]["works_by_prefix_and_type"] += "&sort=created"
    with pytest.raises(ValueError, match="sort"):
        url_builder(make_run_config(), changed, CrossrefScope("10.5194", "posted-content"))("*")


def copernicus():
    return next(r for r in load_platforms() if r["row_id"].startswith("copernicus"))


def test_attribution_records_all_three_signals_and_pattern():
    sel = compile_crossref_selector(copernicus())
    item = {"DOI": "10.5194/egusphere-2025-1", "container-title": ["Atmospheric Chemistry and Physics"],
            "relation": {"is-preprint-of": [{"id": "10.5194/acp-25-1-2025", "id-type": "doi"}]}}
    assert sel.attribution_bases(item, {item["DOI"]}) == [
        "is_preprint_of", "journal_title", "peer_review_is_review_of"]
    assert sel.attribution_bases({"DOI": item["DOI"]}, {item["DOI"]}) == ["peer_review_is_review_of"]
    assert sel.attribution_bases({"DOI": "10.5194/acpd-15-1-2015"}) == ["doi_pattern"]
    assert sel.attribution_bases({"DOI": item["DOI"]}) == []


def test_review_signal_is_joined_and_unattributed_records_retained(tmp_path):
    config, sources, _, logger, roots = run_context(tmp_path)
    rows = [copernicus()]
    crossref_works.run(config, sources, rows, logger, transport=FixtureTransport(), sleeper=lambda _: None, **roots)
    interim = roots["interim_root"] / f"crossref_works__{rows[0]['row_id']}.csv"
    before = {r["doi"]: r for r in read_csv(interim)}
    assert before["10.5194/egusphere-2025-78"]["included"] == "false"
    review = {"DOI": "10.5194/example-review", "type": "peer-review", "relation": {
        "is-review-of": [{"id": "10.5194/egusphere-2025-78", "id-type": "doi"}]}}
    body = {"status": "ok", "message": {"items": [review], "total-results": 1}}
    transport = FixtureTransport({"prefix:10.5194,type:peer-review": [(200, {}, json.dumps(body).encode())]})
    crossref_peer_reviews.run(config, sources, rows, logger, transport=transport, sleeper=lambda _: None, **roots)
    after = {r["doi"]: r for r in read_csv(interim)}
    assert len(after) == len(before)
    assert after["10.5194/egusphere-2025-78"]["attribution_basis"] == "peer_review_is_review_of"
    assert after["10.5194/egusphere-2025-78"]["exclusion_reason"] == ""
    manifest = json.loads((roots["manifest_root"] / config.run_id / f"{config.run_id}.json").read_text())
    entry = manifest["attribution"][rows[0]["row_id"]]
    assert entry["effective_register_status"] == "quantified"
    assert entry["yearly_scope"]["2025"]["coverage"] == "partial_known_scope"


def test_no_signals_is_the_only_register_only_fallback(tmp_path):
    config, sources, _, logger, roots = run_context(tmp_path)
    rows = [copernicus()]
    item = {"DOI": "10.5194/egusphere-2025-999", "type": "posted-content",
            "posted": {"date-parts": [[2025]]}}
    body = {"status": "ok", "message": {"items": [item], "total-results": 1}}
    transport = FixtureTransport({"prefix:10.5194,type:posted-content": [(200, {}, json.dumps(body).encode())]})
    crossref_works.run(config, sources, rows, logger, transport=transport, sleeper=lambda _: None, **roots)
    crossref_peer_reviews.run(config, sources, rows, logger, transport=FixtureTransport(), sleeper=lambda _: None, **roots)
    manifest = json.loads((roots["manifest_root"] / config.run_id / f"{config.run_id}.json").read_text())
    assert manifest["attribution"][rows[0]["row_id"]]["effective_register_status"] == "register_only"
    data = read_csv(roots["interim_root"] / f"crossref_works__{rows[0]['row_id']}.csv")
    record = next(r for r in data if r["doi"] == item["DOI"])
    assert record["included"] == "false"
    assert record["exclusion_reason"] == "no_journal_attribution"


def test_coverage_partial_scope_keeps_partial_year_independent():
    cell = cell_for(row_id="copernicus", year=2026, cutoff=date(2026, 9, 30),
                    register_status="quantified", extraction_status="complete", source_observable=True,
                    in_eligible_range=True, data_status="machine_readable", n_works=2,
                    partial_known_scope=True)
    assert cell.coverage == "partial_known_scope" and cell.partial_year
    assert cell.source_observability_status == "partial_known_scope"


def test_researchhub_reassessment_is_scheduled():
    assert next(r for r in load_excluded() if r["candidate_id"] == "researchhub")["reassess_by"] == "documentation_stabilised_before_release_freeze"


def test_sciety_pagination_keeps_filter_and_request_sidecar(tmp_path):
    config, sources, platforms, logger, roots = run_context(tmp_path)
    rows = [r for r in platforms if r["row_id"] == "prereview"]
    docmap = json.loads((SCIETY / "index__prereview.json").read_bytes())["articles"][0]
    pages = [{"articles": [docmap], "next": "?page=2"},
             {"articles": [], "next": "?page=3"},
             {"articles": [], "next": None}]
    transport = FixtureTransport({"groups%2Fprereview": [(200, {}, json.dumps(p).encode()) for p in pages]})
    outcomes = sciety_evaluations.run(config, sources, rows, logger, transport=transport, sleeper=lambda _: None, **roots)
    assert len(outcomes[0].walk.pages) == 3 and outcomes[0].complete
    assert outcomes[0].walk.completion["rule"] == "sciety_continuation_exhausted"
    sidecars = list((roots["raw_root"] / "sciety" / "evaluations__prereview").rglob("*.request.json"))
    assert len(sidecars) == 3
    for sidecar in sidecars:
        assert json.loads(sidecar.read_text())["parameters"]["publisheraccount"] == ["https://sciety.org/groups/prereview"]
    probe = list((roots["raw_root"] / "sciety" / "index__all").rglob("*.request.json"))   # coverage probe, D-058
    assert len(probe) == 1 and "publisheraccount" not in json.loads(probe[0].read_text())["parameters"]


def test_sciety_mismatch_in_docmap_without_outputs_still_fails(tmp_path):
    config, sources, platforms, logger, roots = run_context(tmp_path)
    rows = [r for r in platforms if r["row_id"] == "prereview"]
    pages = [{"articles": [], "next": "?page=2"},
             {"articles": [{"id": "empty", "publisher": {"account": {"id": "https://sciety.org/groups/elife"}}}]}]
    transport = FixtureTransport({"groups%2Fprereview": [(200, {}, json.dumps(p).encode()) for p in pages]})
    with pytest.raises(PublisherAccountMismatch):
        sciety_evaluations.run(config, sources, rows, logger, transport=transport, sleeper=lambda _: None, **roots)
    assert not list(roots["interim_root"].glob("*.csv"))


@pytest.mark.parametrize("payload", [{"articles": [], "has_more": True},
                                    {"articles": [], "next": 12}, {"articles": None},
                                    {"articles": [], "next": "?a=1", "links": {"next": "?a=2"}}])
def test_sciety_invalid_completion_fails(payload):
    with pytest.raises(ValueError):
        sciety_evaluations.parse_index_page(json.dumps(payload).encode())


def test_full_index_fallback_requires_explicit_configuration(tmp_path):
    config, sources, platforms, logger, roots = run_context(tmp_path)
    rows = [r for r in platforms if r["row_id"] == "prereview"]
    sources["sources"]["sciety"]["retrieval_mode"] = "full_index"
    body = (SCIETY / "index__prereview.json").read_bytes()
    transport = FixtureTransport({"/docmaps/v1/index": [(200, {}, body)]})
    result = sciety_evaluations.run(config, sources, rows, logger, transport=transport, sleeper=lambda _: None, **roots)
    assert result[0].complete and result[0].foreign_docmaps == 1
    assert "publisheraccount" not in transport.requests[0]["url"]
    assert result[0].rows_written == 3
