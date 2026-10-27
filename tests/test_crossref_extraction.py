"""Offline run of the two Crossref extraction stages against fixture pages.

Covers: shared-prefix splitting by DOI regex (never bare prefix), the two
Qeios rows, target flags, versioned relations (boundary test 9), the
Copernicus journal rules and the no-count rule for blocked scopes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.interim import read_csv
from src.extract import crossref_peer_reviews, crossref_works
from src.extract.crossref_common import ExtractionIncomplete
from src.extract.selectors import crossref_scopes, crossref_selectors
from tests.offline import FixtureTransport, crossref_page, run_context


def _run(tmp_path, module, transport=None):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = transport or FixtureTransport()
    outcomes = module.run(run_config, sources, platforms, logger, transport=transport, sleeper=lambda s: None, **roots)
    return outcomes, roots, transport


def _dois(rows):
    return sorted(r["doi"] for r in rows)


# ------------------------------------------------------------------- works
def test_works_stage_splits_shared_prefix_by_stem(tmp_path: Path):
    outcomes, roots, transport = _run(tmp_path, crossref_works)
    interim = roots["interim_root"]
    assert all(o.complete for o in outcomes)
    f1000 = read_csv(interim / "crossref_works__f1000research.csv")
    wellcome = read_csv(interim / "crossref_works__wellcome_open_research.csv")
    gates = read_csv(interim / "crossref_works__gates_open_research.csv")
    assert _dois(f1000) == ["10.12688/f1000research.1001.1", "10.12688/f1000research.1001.2"]
    assert _dois(wellcome) == ["10.12688/wellcomeopenres.2002.1"]
    assert _dois(gates) == ["10.12688/gatesopenres.3003.1"]
    # VeriXiv preprints are posted-content of the same prefix (D-051): the works stage
    # keeps them apart from the F1000 journal-article rows by stem
    verixiv = read_csv(interim / "crossref_works__verixiv.csv")
    assert all(d.startswith("10.12688/verixiv.") for d in _dois(verixiv))
    assert not {d for d in _dois(verixiv)} & set(_dois(gates))
    # every request carried the polite-pool contact and the select list
    assert all("mailto=" in r["url"] and "select=" in r["url"] for r in transport.requests)


def test_works_stage_keeps_qeios_hosted_records_including_withdrawn(tmp_path: Path):
    _, roots, _ = _run(tmp_path, crossref_works)
    rows = read_csv(roots["interim_root"] / "crossref_works__qeios_hosted_works.csv")
    assert _dois(rows) == ["10.32388/aaaa11", "10.32388/bbbb22.2", "10.32388/cccc33", "10.32388/dddd44",
                           "10.32388/eeee55", "10.32388/ffff66"]
    by_doi = {r["doi"]: r for r in rows}
    assert by_doi["10.32388/cccc33"]["title"] == "WITHDRAWN"      # kept here; excluded later by rule
    assert by_doi["10.32388/dddd44"]["posted"] == "2024"           # year precision preserved
    assert by_doi["10.32388/bbbb22.2"]["posted"] == "2025-02"      # month precision preserved
    assert by_doi["10.32388/aaaa11"]["walk_id"] == "w01" and by_doi["10.32388/aaaa11"]["page"] == "1"
    assert by_doi["10.32388/dddd44"]["page"] == "2"
    # the external-works row owns no work records
    assert not (roots["interim_root"] / "crossref_works__qeios_external_works.csv").exists()


def test_works_stage_applies_copernicus_journal_rules(tmp_path: Path):
    _, roots, _ = _run(tmp_path, crossref_works)
    rows = read_csv(roots["interim_root"] / "crossref_works__copernicus_interactive_public_peer_review.csv")
    assert _dois(rows) == ["10.5194/acp-2021-123", "10.5194/acpd-15-1-2015", "10.5194/egusphere-2025-77",
                           "10.5194/egusphere-2025-78", "10.5194/mr-2025-9"]
    # final articles (also those whose stem ends in "d") and non-interactive journals never enter


def test_blocked_scope_withholds_every_dependent_row(tmp_path: Path):
    transport = FixtureTransport(scripted={"prefix:10.12688,type:journal-article": [crossref_page(500)] * 5})
    with pytest.raises(ExtractionIncomplete) as excinfo:
        _run(tmp_path, crossref_works, transport)
    message = str(excinfo.value)
    assert "works__10.12688__journal-article: failed" in message and "f1000research" in message
    interim = tmp_path / "interim"
    assert not (interim / "crossref_works__f1000research.csv").exists()
    assert not (interim / "crossref_works__gates_open_research.csv").exists()
    # unrelated rows were still written
    assert (interim / "crossref_works__qeios_hosted_works.csv").exists()
    manifest = json.loads((tmp_path / "manifests" / "run_test_01" / "run_test_01.json").read_text())
    assert manifest["scopes"]["crossref/works__10.12688__journal-article"]["extraction_status"] == "failed"


# ----------------------------------------------------------------- reviews
def test_review_stage_attributes_by_target_and_flags(tmp_path: Path):
    outcomes, roots, _ = _run(tmp_path, crossref_peer_reviews)
    interim = roots["interim_root"]
    hosted = read_csv(interim / "crossref_peer_reviews__qeios_hosted_works.csv")
    external = read_csv(interim / "crossref_peer_reviews__qeios_external_works.csv")
    unattributed = read_csv(interim / "crossref_peer_reviews__unattributed__10.32388.csv")
    assert _dois(hosted) == ["10.32388/aaaa11.r1", "10.32388/aaaa11.r2", "10.32388/bbbb22.r1", "10.32388/dddd44.r1"]
    assert _dois(external) == ["10.32388/xxxx77.r1", "10.32388/xxxx78.r1", "10.32388/zzzz99.r1"]
    flags = {r["doi"]: r["target_flag"] for r in unattributed}
    assert flags == {"10.32388/yyyy88.r1": "placeholder", "10.32388/yyyy89.r1": "malformed",
                     "10.32388/yyyy90.r1": "self_reference", "10.32388/yyyy91.r1": "missing"}
    # versioned relation is kept as asserted (boundary test 9: canonicalisation happens later)
    versioned = next(r for r in hosted if r["doi"] == "10.32388/bbbb22.r1")
    assert versioned["target_id_raw"] == "10.32388/BBBB22.2"
    # the two Qeios rows never share a review record
    assert not set(_dois(hosted)) & set(_dois(external))


def test_review_stage_uses_separate_review_prefixes(tmp_path: Path):
    _, roots, transport = _run(tmp_path, crossref_peer_reviews)
    interim = roots["interim_root"]
    # F1000Research reviews live under the owner prefix 10.5256 (D-048); one interim line per asserted relation
    assert sorted(set(_dois(read_csv(interim / "crossref_peer_reviews__f1000research.csv")))) == \
        ["10.5256/f1000research.1001.r5001"]
    assert _dois(read_csv(interim / "crossref_peer_reviews__gates_open_research.csv")) == ["10.21956/gatesopenres.3003.r7001"]
    assert any("prefix:10.21956,type:peer-review" in r["url"] for r in transport.requests)
    assert any("prefix:10.5256,type:peer-review" in r["url"] for r in transport.requests)
    assert any("prefix:10.68336,type:peer-review" in r["url"] for r in transport.requests)
    assert any("prefix:10.3310,type:peer-review" in r["url"] for r in transport.requests)


def test_review_stage_requests_only_evaluation_scopes(tmp_path: Path):
    _, _, transport = _run(tmp_path, crossref_peer_reviews)
    # peer-review scopes plus the declared evaluation-record scopes (PCI, D-049: journal-article under 10.24072)
    assert all("type:peer-review" in r["url"] or "prefix:10.24072,type:journal-article" in r["url"]
               for r in transport.requests)
    assert any("type:peer-review" in r["url"] for r in transport.requests)


# --------------------------------------------------------------- selectors
def test_scopes_are_distinct_prefix_type_pairs():
    from src.common.register import load_platforms
    selectors = crossref_selectors(load_platforms())
    works = crossref_scopes(selectors, "works")
    ids = [s.scope_id for s in works]
    assert len(ids) == len(set(ids))
    assert ids.count("works__10.12688__journal-article") == 1
    reviews = crossref_scopes(selectors, "reviews")
    review_ids = [s.scope_id for s in reviews]
    assert len(review_ids) == len(set(review_ids))
    for scope_id in ("works__10.21956__peer-review", "works__10.5256__peer-review", "works__10.68336__peer-review",
                     "works__10.3310__peer-review", "works__10.24072__journal-article"):
        assert scope_id in review_ids
    assert all(s.record_type == "peer-review" or s.scope_id == "works__10.24072__journal-article" for s in reviews)
