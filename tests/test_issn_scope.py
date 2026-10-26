"""ISSN-based Crossref scopes and owner-prefix semantics.

The Crossref ``prefix`` filter selects by the *current owner* prefix. Two
register consequences are pinned here:

* MedEdPublish: the 10.15694 records passed to F1000 with the title and are
  retrieved inside the 10.12688 walk; a 10.15694 scope is not declared.
* Emerald Open Research: articles are retrieved by journal ISSN and
  selected by ``^10\\.1108/eor-``; the completion rule is the one every
  Crossref walk uses (short page and total-results check).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.common.register import load_platforms, platforms_by_row_id
from src.extract import crossref_works
from src.extract.selectors import (CrossrefScope, SelectorError, compile_crossref_selector,
                                   crossref_scopes, crossref_selectors)
from src.extract.crossref_common import url_builder
from tests.offline import FixtureTransport, make_run_config, run_context

SELECTORS = crossref_selectors(load_platforms())
WORK_SCOPES = crossref_scopes(SELECTORS, "works")
SCOPE_IDS = {s.scope_id for s in WORK_SCOPES}


def test_scope_ids_and_kinds():
    assert "works__issn_2631-3952__journal-article" in SCOPE_IDS
    assert "works__10.15694__journal-article" not in SCOPE_IDS
    assert "works__10.15694__posted-content" not in SCOPE_IDS
    assert "works__10.35241__journal-article" not in SCOPE_IDS
    issn_scope = CrossrefScope("issn:2631-3952", "journal-article")
    assert issn_scope.kind == "issn" and issn_scope.issn == "2631-3952" and issn_scope.prefix == ""
    prefix_scope = CrossrefScope("10.12688", "journal-article")
    assert prefix_scope.kind == "prefix" and prefix_scope.prefix == "10.12688" and prefix_scope.issn == ""
    # peer-review scopes are never ISSN-based
    assert all(s.kind == "prefix" for s in crossref_scopes(SELECTORS, "reviews"))


def test_issn_scope_url_uses_issn_filter():
    from src.common.config import load_sources_config
    url = url_builder(make_run_config(), load_sources_config(), CrossrefScope("issn:2631-3952", "journal-article"))("*")
    assert "filter=issn:2631-3952,type:journal-article" in url
    assert "prefix:" not in url
    assert "cursor=%2A" in url or "cursor=*" in url


def test_register_rows():
    rows = platforms_by_row_id(load_platforms())
    emerald = rows["emerald_open_research"]
    assert emerald["extraction_selector"]["crossref"]["issn"] == "2631-3952"
    assert emerald["extraction_selector"]["crossref"]["record_types"] == ["journal-article"]
    assert emerald["doi_pattern"] == r"^10\.1108/eor-"
    assert emerald["doi_version_pattern"] is None
    assert emerald["data_status"] == "machine_readable"
    assert emerald["status"] == "closed" and emerald["coverage_end_year"] == 2023  # D-014 unchanged
    meded = rows["meded_publish"]
    assert meded["extraction_selector"]["crossref"]["prefix"] == ["10.12688"]
    assert meded["doi_pattern"] == r"^10\.(15694|12688)/mep\."
    assert meded["data_status"] == "machine_readable"
    assert meded["coverage_start_year"] == 2016


def test_issn_selector_requires_doi_regex_and_valid_issn():
    base = {"row_id": "x", "register_status": "quantified", "data_source": "crossref",
            "extraction_selector": {"crossref": {"issn": "2631-3952", "record_types": ["journal-article"]}}}
    with pytest.raises(SelectorError):
        compile_crossref_selector(base)
    bad = {**base, "extraction_selector": {"crossref": {"issn": "2631-395", "record_types": ["journal-article"],
                                                          "doi_regex": "^10\\.1108/eor-"}}}
    with pytest.raises(SelectorError):
        compile_crossref_selector(bad)
    ok = {**base, "extraction_selector": {"crossref": {"issn": "2631-3952", "record_types": ["journal-article"],
                                                         "doi_regex": "^10\\.1108/eor-"}}}
    sel = compile_crossref_selector(ok)
    assert sel.issns == ["2631-3952"] and sel.work_keys() == ["issn:2631-3952"]


def _interim(roots, name):
    path = roots["interim_root"] / name
    assert path.exists(), name
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_issn_walk_splits_emerald_records_by_doi_regex(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = FixtureTransport()
    crossref_works.run(run_config, sources, platforms, logger, transport=transport,
                       sleeper=lambda s: None, **roots)
    urls = [r["url"] for r in transport.requests]
    assert any("filter=issn:2631-3952,type:journal-article" in u for u in urls)
    assert not any("prefix:10.15694" in u or "prefix:10.35241" in u for u in urls)
    rows = _interim(roots, "crossref_works__emerald_open_research.csv")
    dois = sorted(r["doi"] for r in rows)
    assert dois == ["10.1108/eor-01-2023-0001", "10.1108/eor-02-2023-0002", "10.1108/eor-03-2023-0018",
                    "10.1108/eor-05-2023-0007", "10.1108/eor-06-2023-0009"]
    assert all(r["platform_id"] == "emerald_open_research" and r["exclusion_reason"] == "" for r in rows)
    assert all(r["issued"].startswith(("2019", "2021", "2022", "2023")) for r in rows)


def test_transferred_title_records_arrive_through_owner_prefix(tmp_path: Path):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    crossref_works.run(run_config, sources, platforms, logger, transport=FixtureTransport(),
                       sleeper=lambda s: None, **roots)
    rows = _interim(roots, "crossref_works__meded_publish.csv")
    by_doi = {r["doi"]: r for r in rows}
    assert "10.15694/mep.2019.000158.1" in by_doi
    assert by_doi["10.15694/mep.2019.000158.1"]["prefix"] == "10.12688"  # owner prefix, not the DOI string
    assert "10.12688/mep.19344.1" in by_doi
    # the F1000Research record in the same walk is not attributed to MedEdPublish
    assert not any(d.startswith("10.12688/f1000research") for d in by_doi)


def test_emerald_counts_by_original_issued_year(pipeline_outputs):
    cells = pipeline_outputs.cells("works_by_row_year", row_id="emerald_open_research")
    counts = {int(c["year"]): c["count"] for c in cells}
    assert counts[2019] == "2" and counts[2020] == "0" and counts[2021] == "1"
    assert counts[2022] == "1" and counts[2023] == "1"
    assert all(c["extraction_status"] == "complete" for c in cells if c["count"] != "")
    assert counts[2024] == "" and counts[2018] == ""  # outside 2019–2023 (D-014)
    works = pipeline_outputs.processed / "works_included.csv"
    with works.open(encoding="utf-8", newline="") as handle:
        included = [r for r in csv.DictReader(handle) if r["row_id"] == "emerald_open_research" and r["included"] == "true"]
    # the primaries carry no version suffix: canonical id = the DOI itself
    assert sorted(r["canonical_work_id"] for r in included) == sorted(f"doi:{r['work_doi']}" for r in included)
