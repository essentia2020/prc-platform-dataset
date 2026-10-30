"""Run run_20261026_01 findings: owner-prefix scopes, evaluation records deposited as
journal-article, companion items, repeated-slash DOIs, asserted_by, and the register
prefix check (D-047 … D-053).  Everything runs offline against tests/fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.identifiers import canonical_doi, collapse_repeated_slashes, has_repeated_slash, identifier_flag
from src.common.interim import CROSSREF_REVIEW_COLUMNS, read_csv
from src.common.register import load_platforms
from src.extract import crossref_peer_reviews, crossref_works
from src.extract.selectors import crossref_scopes, crossref_selectors, review_targets
from tests.offline import FixtureTransport, run_context
from tools import check_register_prefixes as prefix_check

SCOPE_IDS = {s.scope_id for s in crossref_scopes(crossref_selectors(load_platforms()))}


def _run(tmp_path: Path, module):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = FixtureTransport()
    outcomes = module.run(run_config, sources, platforms, logger, transport=transport, sleeper=lambda _: None,
                          **roots)
    return outcomes, roots, transport


def _rows(roots, name):
    return read_csv(roots["interim_root"] / name)


# ----------------------------------------------------------------- scopes (D-047, D-048)
def test_owner_prefix_scopes_are_declared():
    for scope in ("works__10.3310__journal-article", "works__10.3310__peer-review",
                  "works__10.68336__journal-article", "works__10.68336__peer-review",
                  "works__10.5256__peer-review", "works__10.24072__journal-article"):
        assert scope in SCOPE_IDS, scope
    # the wrong NIHR declaration of run_20261026_01 is gone
    rows = {r["row_id"]: r for r in load_platforms()}
    nihr = rows["nihr_open_research"]
    assert nihr["doi_prefix"] == "10.3310" and nihr["extraction_selector"]["crossref"]["prefix"] == "10.3310"
    assert rows["open_research_europe"]["extraction_selector"]["crossref"]["prefix"] == "10.68336"
    assert rows["f1000research"]["extraction_selector"]["crossref"]["review_doi_prefix"] == "10.5256"


def test_review_doi_prefix_accepts_a_list():
    rows = load_platforms()
    row = next(r for r in rows if r["row_id"] == "hrb_open_research")
    sel = next(s for s in crossref_selectors([row]))
    assert sel.review_prefixes() == ["10.12688", "10.21956"]
    row2 = json.loads(json.dumps(row))
    row2["extraction_selector"]["crossref"]["review_doi_prefix"] = ["10.21956", "10.5256"]
    sel2 = next(s for s in crossref_selectors([row2]))
    assert sel2.review_prefixes() == ["10.12688", "10.21956", "10.5256"]
    assert sel2.review_doi_prefix == "10.21956"


def test_nihr_and_ore_records_are_retrieved_under_their_owner_prefixes(tmp_path: Path):
    _, roots, transport = _run(tmp_path, crossref_works)
    nihr = _rows(roots, "crossref_works__nihr_open_research.csv")
    assert sorted(r["doi"] for r in nihr) == ["10.3310/nihropenres.13716.1", "10.3310/nihropenres.13716.3"]
    # the NIHR Journals Library record under the shared prefix is not selected
    assert "10.3310/abcd1234" not in {r["doi"] for r in nihr}
    ore = _rows(roots, "crossref_works__open_research_europe.csv")
    assert [r["doi"] for r in ore] == ["10.12688/openreseurope.13104.1"]
    assert ore[0]["prefix"] == "10.68336"       # owner prefix differs from the DOI string
    assert any("prefix%3A10.3310" in r["url"] or "prefix:10.3310" in r["url"] for r in transport.requests)


def test_review_stage_walks_declared_review_prefixes(tmp_path: Path):
    _, roots, _ = _run(tmp_path, crossref_peer_reviews)
    f1000 = _rows(roots, "crossref_peer_reviews__f1000research.csv")
    assert {r["doi"] for r in f1000} == {"10.5256/f1000research.1001.r5001"}
    assert len(f1000) == 2 and {r["asserted_by"] for r in f1000} == {"subject", "object"}
    nihr = _rows(roots, "crossref_peer_reviews__nihr_open_research.csv")
    assert {r["doi"] for r in nihr} == {"10.3310/nihropenres.15251.r36677"}
    ore = _rows(roots, "crossref_peer_reviews__open_research_europe.csv")
    assert {r["doi"] for r in ore} == {"10.21956/openreseurope.14256.r26750"}


# -------------------------------------------------------- asserted_by (item 6)
def test_relation_lines_carry_asserted_by_and_duplicates_are_kept(tmp_path: Path):
    assert CROSSREF_REVIEW_COLUMNS[-2:] == ["asserted_by", "target_doi_flag"]
    _, roots, _ = _run(tmp_path, crossref_peer_reviews)
    wellcome = _rows(roots, "crossref_peer_reviews__wellcome_open_research.csv")
    lines = [(r["doi"], r["target_id_raw"], r["asserted_by"]) for r in wellcome]
    assert lines == [("10.21956/wellcomeopenres.2002.r6001", "10.12688/wellcomeopenres.2002.1", "subject"),
                     ("10.21956/wellcomeopenres.2002.r6001", "10.12688/wellcomeopenres.2002.1", "object")]


def test_review_targets_expose_asserted_by():
    item = {"DOI": "10.21956/wellcomeopenres.2002.r6001", "type": "peer-review",
            "relation": {"is-review-of": [{"id": "10.12688/wellcomeopenres.2002.1", "id-type": "doi",
                                           "asserted-by": "object"},
                                          {"id": "10.12688/wellcomeopenres.2002.1", "id-type": "doi"}]}}
    targets = review_targets(item)
    assert [t.asserted_by for t in targets] == ["object", ""]
    assert all(t.flag == "" and t.doi_flag == "" and t.doi == "10.12688/wellcomeopenres.2002.1" for t in targets)


# ---------------------------------------------------- repeated slashes (D-053)
def test_repeated_slash_helpers():
    raw = "10.15694//mep.2021.000035.1"
    assert has_repeated_slash(raw) and identifier_flag(raw) == "repeated_slash"
    assert collapse_repeated_slashes(raw) == "10.15694/mep.2021.000035.1"
    assert identifier_flag("10.15694/mep.2021.000035.1") == ""
    assert canonical_doi(raw, r"^(10\.15694/mep\.\d{4}\.\d+)\.\d+$") == "10.15694/mep.2021.000035"


def test_repeated_slash_targets_are_flagged_not_blocked():
    item = {"DOI": "10.21956//mep.18871.r26923", "type": "peer-review",
            "relation": {"is-review-of": [{"id": "10.15694//mep.2021.000035.1", "id-type": "doi",
                                           "asserted-by": "subject"}]}}
    (target,) = review_targets(item)
    assert target.flag == "" and target.doi_flag == "repeated_slash"
    assert target.doi == "10.15694/mep.2021.000035.1" and target.raw == "10.15694//mep.2021.000035.1"


def test_malformed_meded_work_and_reviews_are_kept(tmp_path: Path):
    _, roots, _ = _run(tmp_path, crossref_works)
    meded = {r["doi_original"]: r for r in _rows(roots, "crossref_works__meded_publish.csv")}
    assert "10.15694//mep.2021.000035.1" in meded
    row = meded["10.15694//mep.2021.000035.1"]
    assert row["doi"] == "10.15694/mep.2021.000035.1" and row["doi_flag"] == "repeated_slash"
    _, roots2, _ = _run(tmp_path / "r", crossref_peer_reviews)
    reviews = [r for r in _rows(roots2, "crossref_peer_reviews__meded_publish.csv") if "//" in r["doi_original"]]
    assert len(reviews) == 2
    assert all(r["target_flag"] == "" and r["target_doi_flag"] == "repeated_slash" for r in reviews)
    assert all(r["target_id_raw"] == "10.15694//mep.2021.000035.1" for r in reviews)


def test_malformed_meded_work_is_counted_and_logged(pipeline_outputs):
    out = pipeline_outputs
    works = {w["counting_record_id"]: w for w in out.works("meded_publish")}
    # the asserted (raw) identifier is kept as the counting record id; the canonical id is collapsed
    assert "10.15694//mep.2021.000035.1" in works
    w = works["10.15694//mep.2021.000035.1"]
    assert w["canonical_work_id"] == "doi:10.15694/mep.2021.000035" and w["work_doi"] == "10.15694/mep.2021.000035"
    assert w["counting_year"] == "2021" and w["included"] == "true"
    recs = out.records("meded_publish")
    flagged = [r for r in recs if r["identifier_flag"] == "repeated_slash"]
    assert {r["source_record_id"] for r in flagged} == {"10.15694//mep.2021.000035.1",
                                                        "10.21956/mep.18871.r26923", "10.21956/mep.18871.r26924"}
    assert [r for r in flagged if r["event_kind"] == "posting"][0]["work_id"] == "doi:10.15694//mep.2021.000035.1"
    assert all(r["reviewed_canonical_work_id"] == "doi:10.15694/mep.2021.000035"
               for r in flagged if r["relation_type"] == "is-review-of")
    dq = [r for r in read_csv(out.processed / "data_quality_log.csv")
          if r["run_id"] == out.run_config.run_id and r["row_id"] == "meded_publish"
          and r["issue_type"] == "malformed_doi" and r["status"] == "observed"]
    assert len(dq) == 1 and int(dq[0]["n_records_affected"]) >= 3


# --------------------------------------------------- PCI evaluation records (D-049)
def test_pci_recommendations_are_evaluation_records(pipeline_outputs):
    out = pipeline_outputs
    recs = out.records("pci_recommendations")
    evaluations = [r for r in recs if r["event_kind"] == "evaluation"]
    assert sorted(r["source_record_id"] for r in evaluations) == ["10.24072/pci.ecology.100500",
                                                                  "10.24072/pci.evolbiol.100844"]
    assert all(r["source_record_type"] == "journal-article" for r in evaluations)
    assert all(r["canonical_evaluation_id"] == "doi:" + r["source_record_id"] for r in evaluations)
    # reviews, decisions and Peer Community Journal articles are neither works nor evaluations of the row
    assert not [r for r in recs if r["event_kind"] == "posting"]
    assert not [r for r in recs if r["source_record_id"].endswith((".rev11", ".d1")) or "pcjournal" in r["source_record_id"]]
    works = out.works("pci_recommendations")
    assert sorted(w["canonical_work_id"] for w in works) == ["doi:10.1101/2024.05.05.500000",
                                                              "doi:10.1101/2024.08.08.607164"]
    assert {w["counting_year"] for w in works} == {"2024", "2025"}
    assert out.analysis_manifest["rows"]["pci_recommendations"]["selector_no_match"] is False


def test_pci_scope_is_shared_between_stages(tmp_path: Path):
    _, roots, transport = _run(tmp_path, crossref_works)
    assert not (roots["interim_root"] / "crossref_works__pci_recommendations.csv").exists() or \
        _rows(roots, "crossref_works__pci_recommendations.csv") == []
    n_before = len(transport.requests)
    run_config, sources, platforms, logger, _ = run_context(tmp_path)
    crossref_peer_reviews.run(run_config, sources, platforms, logger, transport=transport, sleeper=lambda _: None,
                              **roots)
    pci = _rows(roots, "crossref_peer_reviews__pci_recommendations.csv")
    assert sorted(r["doi"] for r in pci) == ["10.24072/pci.ecology.100500", "10.24072/pci.evolbiol.100844"]
    assert all(r["type"] == "journal-article" for r in pci)
    # the completed journal-article walk is reused, not requested again
    assert not any("prefix%3A10.24072%2Ctype%3Ajournal-article" in r["url"] or
                   "prefix:10.24072,type:journal-article" in r["url"] for r in transport.requests[n_before:])


# ------------------------------------------------- JMIRx Med companions (D-050)
def test_jmirx_companion_items_are_kept_but_not_counted(pipeline_outputs):
    out = pipeline_outputs
    works = out.works("jmirx_med")
    assert [w["counting_record_id"] for w in works if w["included"] == "true"] == ["10.2196/35862"]
    assert sorted(w["work_doi"] for w in works if w["exclusion_reason"] == "companion_item") == \
        ["10.2196/36198", "10.2196/36207"]
    recs = {r["source_record_id"]: r for r in out.records("jmirx_med") if r["event_kind"] == "final_article"}
    assert recs["10.2196/36207"]["exclusion_reason"] == "companion_item"
    assert recs["10.2196/36198"]["exclusion_reason"] == "companion_item"
    assert recs["10.2196/35862"]["exclusion_reason"] == ""
    assert "10.2196/40000" not in recs      # other JMIR journal
    dq = [r for r in read_csv(out.processed / "data_quality_log.csv")
          if r["run_id"] == out.run_config.run_id and r["row_id"] == "jmirx_med"
          and r["issue_type"] == "companion_record" and r["status"] == "observed"]
    assert len(dq) == 1 and dq[0]["n_records_affected"] == "2"


def test_jmirx_row_declares_no_peer_review_type():
    rows = {r["row_id"]: r for r in load_platforms()}
    assert rows["jmirx_med"]["extraction_selector"]["crossref"]["record_types"] == ["journal-article"]
    assert "companion_title_regex" in rows["jmirx_med"]["extraction_selector"]["crossref"]


# ----------------------------------------------------------- VeriXiv (D-051)
def test_verixiv_selector_is_enabled_and_provisional(pipeline_outputs):
    rows = {r["row_id"]: r for r in load_platforms()}
    v = rows["verixiv"]
    assert "selector_status" not in v["extraction_selector"]["crossref"]
    assert v["register_status"] == "quantified" and v["provisional"] is True
    assert v["extraction_selector"]["crossref"]["record_types"] == ["posted-content", "peer-review"]
    out = pipeline_outputs
    assert out.analysis_manifest["rows"]["verixiv"]["extraction_status"] == "complete"
    # provisional: present in the row table, absent from the headline group tables
    assert out.cells("works_by_row_year", row_id="verixiv")
    for name in ("works_by_class_year", "unique_works_by_class_year"):
        assert all(r.get("row_id") is None for r in out.table(name))


# -------------------------------------------------- register prefix check (item 11)
class _ResolverTransport:
    """Answers GET /works/<doi> from a dict; records every URL."""

    def __init__(self, records):
        self.records = records
        self.urls = []

    def __call__(self, url, headers, timeout):
        self.urls.append(url)
        doi = url.split("/works/", 1)[1].split("?", 1)[0]
        from urllib.parse import unquote
        rec = self.records.get(unquote(doi).lower())
        if rec is None:
            return 404, {}, b"Resource not found."
        return 200, {}, json.dumps({"status": "ok", "message": rec}).encode()


def test_register_prefix_check_reports_mismatches_offline():
    rows = load_platforms()
    records = {
        "10.3310/nihropenres.13716.3": {"prefix": "10.3310", "member": "6221", "type": "journal-article", "ISSN": ["2633-4402"]},
        "10.3310/nihropenres.15251.r36677": {"prefix": "10.3310", "member": "6221", "type": "peer-review"},
        "10.12688/openreseurope.13104.1": {"prefix": "10.68336", "member": "13904", "type": "journal-article"},
        "10.21956/openreseurope.14256.r26750": {"prefix": "10.68336", "member": "13904", "type": "peer-review"},
        "10.12688/f1000research.15931.1": {"prefix": "10.12688", "member": "2560", "type": "journal-article"},
        "10.5256/f1000research.17815.r38403": {"prefix": "10.5256", "member": "2560", "type": "peer-review"},
    }
    transport = _ResolverTransport(records)
    waits: list[float] = []
    results = prefix_check.run_check(rows, transport, base_url="https://api.crossref.org", mailto="x@example.org",
                                     user_agent="t/1", only={"nihr_open_research", "open_research_europe", "f1000research"},
                                     sleep=waits.append)
    assert waits and all(w == prefix_check.REQUEST_SPACING for w in waits)   # lookups are spaced, never a burst
    by_row = {r.row_id: r for r in results}
    assert {r.status for r in by_row.values()} == {"ok"}
    assert prefix_check.exit_code(results) == 0
    assert all("mailto=" in u for u in transport.urls)
    # the run_20261026_01 declaration (NIHR under 10.12688) is reported as a mismatch
    wrong = json.loads(json.dumps(rows))
    for r in wrong:
        if r["row_id"] == "nihr_open_research":
            r["extraction_selector"]["crossref"]["prefix"] = "10.12688"
            r["extraction_selector"]["crossref"]["review_doi_prefix"] = "10.21956"
    results = prefix_check.run_check(wrong, _ResolverTransport(records), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", only={"nihr_open_research"},
                                     sleep=lambda _w: None)
    assert results[0].status == "mismatch" and prefix_check.exit_code(results) == 1
    assert {c.role for c in results[0].checks if c.status == "mismatch"} == {"work", "review"}
    assert "10.3310" in prefix_check.format_report(results)
    # an unresolvable sample DOI is inconclusive, never silently ok
    results = prefix_check.run_check(rows, _ResolverTransport({}), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", only={"nihr_open_research"},
                                     sleep=lambda _w: None)
    assert results[0].status == "unresolved" and prefix_check.exit_code(results) == 2
    assert all("HTTP 404" in c.note for c in results[0].checks)


def test_register_prefix_check_retries_throttled_lookups():
    class Throttled(_ResolverTransport):
        def __init__(self, records, failures):
            super().__init__(records)
            self.failures = failures

        def __call__(self, url, headers, timeout):
            if self.failures:
                self.failures -= 1
                self.urls.append(url)
                return 429, {}, b""
            return super().__call__(url, headers, timeout)

    rows = load_platforms()
    records = {"10.3310/nihropenres.13716.3": {"prefix": "10.3310", "member": "6221", "type": "journal-article"},
               "10.3310/nihropenres.15251.r36677": {"prefix": "10.3310", "member": "6221", "type": "peer-review"}}
    waits: list[float] = []
    results = prefix_check.run_check(rows, Throttled(records, 2), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", only={"nihr_open_research"},
                                     sleep=waits.append)
    assert results[0].status == "ok"
    assert waits[:2] == list(prefix_check.RETRY_WAITS[:2])
    # exhausted retries are inconclusive, reported with the status code
    results = prefix_check.run_check(rows, Throttled(records, 50), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", only={"nihr_open_research"},
                                     sleep=lambda _w: None)
    assert results[0].status == "unresolved" and all("HTTP 429" in c.note for c in results[0].checks)


def test_every_quantified_crossref_row_declares_a_sample_work_doi_or_is_reported():
    rows = load_platforms()
    results = prefix_check.run_check(rows, _ResolverTransport({}), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", sleep=lambda _w: None)
    quantified = {r["row_id"] for r in rows if r["register_status"] == "quantified"
                  and r["data_source"] in ("crossref", "both")}
    assert {r.row_id for r in results} == quantified
    for r in results:
        assert r.status in ("unresolved", "unchecked")
        for c in r.checks:
            if not c.doi and r.row_id == "emerald_open_research":
                assert c.role == "review" and c.status == "unchecked"       # D-046: reviews withdrawn at source
            elif not c.doi:
                # external-target rows have no work DOI of their own; every other sample is declared
                assert c.status == "not_applicable" and c.role == "work", (r.row_id, c)
    # every quantified Crossref row declares a sample work DOI (or has external works) and a sample review DOI
    # wherever it walks evaluation records
    for r in results:
        roles = {c.role: c for c in r.checks}
        assert roles["work"].doi or roles["work"].status == "not_applicable", r.row_id
        if "review" in roles:
            assert roles["review"].doi or r.row_id == "emerald_open_research", r.row_id    # D-046: withdrawn
