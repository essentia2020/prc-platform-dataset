"""Copernicus row: hand-verified journal list, three DOI regimes, EGUsphere attribution rule (D-027)."""

from __future__ import annotations

import pytest

from src.common.register import load_platforms, platforms_by_row_id
from src.extract.selectors import compile_crossref_selector

ROW = "copernicus_interactive_public_peer_review"


@pytest.fixture(scope="module")
def selector():
    return compile_crossref_selector(platforms_by_row_id(load_platforms())[ROW])


@pytest.fixture(scope="module")
def row():
    return platforms_by_row_id(load_platforms())[ROW]


def test_every_journal_has_its_own_evidence_and_selector(row):
    journals = row["extraction_selector"]["crossref"]["journals"]
    assert len(journals) >= 20
    for j in journals:
        assert j["evidence_url"].startswith("https://www.") and "/peer_review/" in j["evidence_url"], j["journal_id"]
        assert j["verified_on"] and j["interactive_public_peer_review"] is True
        assert len(j["discussion_selector"]["journal_specific_doi_regex"]) == 2
    assert len({j["journal_id"] for j in journals}) == len(journals)
    excluded = row["extraction_selector"]["crossref"]["journals_not_using_interactive_review"]
    assert {j["title"] for j in excluded}.isdisjoint({j["title"] for j in journals})
    assert all(j["evidence_url"].startswith("https://www.") for j in excluded)


@pytest.mark.parametrize("doi, journal", [
    ("10.5194/acp-2021-123", "acp"),          # journal discussion forum regime
    ("10.5194/acpd-15-1-2015", "acp"),        # former Discussions journal regime
    ("10.5194/esurfd-3-1-2015", "esurf"),
    ("10.5194/mr-2025-9", "mr"),
    ("10.5194/essd-2026-619", "essd"),
])
def test_journal_specific_regimes(selector, doi, journal):
    assert selector.journal_for(doi) == journal
    assert selector.doi_in_scope(doi)


@pytest.mark.parametrize("doi", [
    "10.5194/acp-25-1-2025",      # final article
    "10.5194/esd-12-1-2021",      # final article of a journal whose stem ends in d
    "10.5194/gmd-14-1-2021",
    "10.5194/aab-60-1-2017",      # journal verified as conventional review
    "10.5194/aab-2020-1",         # conventional-review journal, discussion-like pattern
    "10.5194/isprs-archives-XLII-2-W13-1-2019",
    "10.5194/ejm-2020-5",
])
def test_out_of_series_dois(selector, doi):
    assert selector.journal_for(doi) is None
    assert not selector.doi_in_scope(doi)


def test_egusphere_attribution_rule(selector):
    attributed = {"DOI": "10.5194/egusphere-2025-77", "type": "posted-content",
                  "relation": {"is-preprint-of": [{"id": "10.5194/acp-25-1-2025", "id-type": "doi"}]}}
    by_title = {"DOI": "10.5194/egusphere-2025-79", "type": "posted-content",
                "container-title": ["Atmospheric Chemistry and Physics"]}
    standalone = {"DOI": "10.5194/egusphere-2025-78", "type": "posted-content"}
    foreign = {"DOI": "10.5194/egusphere-2025-80", "type": "posted-content",
               "relation": {"is-preprint-of": [{"id": "10.5194/aab-68-1-2025", "id-type": "doi"}]}}
    assert selector.attribute_journal(attributed) == ("acp", "egusphere_is_preprint_of")
    assert selector.attribute_journal(by_title) == ("acp", "egusphere_container_title")
    assert selector.attribute_journal(standalone) == ("", "egusphere_unattributed")
    assert selector.attribute_journal(foreign) == ("", "egusphere_unattributed")
    assert selector.attribute_journal({"DOI": "10.5194/acp-2021-123"}) == ("acp", "journal_specific_doi")
    assert selector.attribute_journal({"DOI": "10.5194/acp-25-1-2025"}) == ("", "out_of_scope")


def test_row_is_quantified_with_discussion_preprint_counting(row):
    assert row["register_status"] == "quantified"
    assert row["counting_event"] == "first_public_posting"
    assert row["extraction_selector"]["crossref"]["selector_status"] == "verified_journal_list"
    assert row["extraction_selector"]["crossref"]["egusphere_regime"]["attribution_status"] == "pending_run_confirmation"
