"""User-ruling consistency checks; no retrieval or network calls."""

import copy
import re

import pytest
import yaml

from src.common import config, register


@pytest.fixture
def rows():
    return register.platforms_by_row_id(register.load_platforms())


def test_decision_attribution(repo_root):
    text = (repo_root / "docs/decisions.md").read_text(encoding="utf-8")
    ids = [f"D-{n:03d}" for n in range(1, 36)] + [f"Q-{n}" for n in range(1, 4)]
    assert "decided_by: user" not in text and "Decided by:** user" not in text
    for decision in ids:
        section = re.search(rf"^## {decision}\b.*?(?=^## |\Z)", text, re.M | re.S)
        assert section, decision
        body = section.group()
        assert "decided_by: researcher" in body or "**Decided by:** researcher" in body, decision
        assert "**Decision:**" in section.group(), decision


def test_current_sites_keep_both_doi_stems(rows):
    pairs = {
        "health_open_research": ("healthopenres", "amrcopenres"),
        "open_research_africa": ("openresafrica", "aasopenres"),
    }
    for row_id, stems in pairs.items():
        row = rows[row_id]
        assert row["model_note"]
        for stem in stems:
            assert re.match(row["doi_pattern"], f"10.12688/{stem}.123.1")


def test_gates_and_verixiv_are_separate_series(rows):
    gates, preprint = rows["gates_open_research"], rows["verixiv"]
    assert gates["organisation_id"] == preprint["organisation_id"] == "gates_f1000"
    assert gates["coverage_end_year"] == 2024
    assert gates["prc_configuration"] == "approval_threshold"
    assert gates["counting_event"] == "first_public_posting"
    assert not re.match(gates["doi_pattern"], "10.12688/verixiv.123.1")
    assert preprint["model_since"] == 2024
    assert preprint["counting_event"] == "first_public_posting"
    assert len(preprint["eligibility_events"]) == 2
    assert "public review" in preprint["eligibility_events"][1]
    assert preprint["provisional"] is True
    # D-051: deposit confirmed in run_20261026_01, selector enabled, row quantified and provisional
    assert preprint["register_status"] == "quantified"
    assert preprint["extraction_selector"]["crossref"].get("selector_status", "") == ""
    assert preprint["extraction_selector"]["crossref"]["record_types"] == ["posted-content", "peer-review"]


def test_overlap_contract_is_pair_specific(repo_root):
    plan = (repo_root / "docs/analysis_plan.md").read_text(encoding="utf-8")
    assert "overlap is expected, reported and" in plan
    assert "empty by construction for the two Qeios rows" in plan


def test_copernicus_uses_discussion_preprints(rows):
    row = rows["copernicus_interactive_public_peer_review"]
    assert row["counting_event"] == "first_public_posting"
    assert "discussion preprint" in row["eligibility_events"][0]
    assert "SciPost" in row["configuration_note"]
    assert row["register_status"] == "quantified"   # D-027: journal list verified under the user ruling, 2026-10-20
    assert row["provisional"] is False


def test_pending_selectors_cannot_publish_counts():
    data = yaml.safe_load(register.PLATFORMS_YAML.read_text(encoding="utf-8"))
    changed = copy.deepcopy(data["platforms"])
    for row in changed:
        if row["row_id"] == "gates_open_research":      # any quantified Crossref row
            row["extraction_selector"]["crossref"]["selector_status"] = "pending_confirmation"
    with pytest.raises(register.RegisterError, match="pending selector"):
        register.validate_platforms(changed, data["register_meta"])


def test_jmirx_ruling(rows):
    row = rows["jmirx_med"]
    assert row["initiation_class"] == "mixed"
    assert row["classification_confidence"] == row["configuration_confidence"] == "medium"
    assert row["prc_configuration"] == "core_publish_first"
    assert row["prc_role"] == "overlay_journal"
    assert row["provisional"] is False


def test_access_microbiology_start_is_run_derived(rows):
    row = rows["access_microbiology"]
    assert row["coverage_start_year"] is None
    assert row["model_since"] is None
    assert row["extraction_selector"]["coverage_start_policy"] == "first_qualifying_event_year_from_completed_run"
    assert row["provisional"] is False


def test_other_accepted_rulings(rows):
    assert rows["emerald_open_research"]["status"] == "closed"
    assert rows["emerald_open_research"]["coverage_end_year"] == 2023
    assert rows["prereview"]["initiation_class"] == "community_initiated"
    for name in ("biophysics_colab", "life_science_editors_foundation", "life_science_editors", "the_unjournal"):
        assert rows[name]["initiation_class"] == "mixed"
    for name in ("asapbio_crowd_review", "asapbio_scielo_crowd_review"):
        assert rows[name]["status"] == "dormant"
    assert rows["arcadia_science"]["status"] == "active"
    assert "December 2025" in rows["arcadia_science"]["model_note"]
    assert rows["peerref"]["status"] == "dormant"
    assert rows["peerref"]["coverage_end_year"] is None
    for name in ("metaror", "the_unjournal"):                           # D-063, D-064
        assert rows[name]["data_source"] == "both"
        assert rows[name]["extraction_selector"]["crossref"]["role"] == "primary"
        assert rows[name]["extraction_selector"]["sciety"]["role"] == "cross_check"
        assert rows[name]["review_to_object_relation"] == "crossref_is_review_of"
    assert rows["metaror"]["data_status"] == "machine_readable"
    assert rows["the_unjournal"]["data_status"] == "partial_coverage"
    provisional = {row_id for row_id, row in rows.items() if row["provisional"]}
    assert provisional == {"verixiv",                                   # D-051
                           "stosunki_miedzynarodowe", "nuclear_science_technology_open_research", "digital_twin",
                           "molecular_psychology", "materials_open_research", "cobot",
                           "bioethics_open_research"}                   # D-052


def test_cutoff_and_release_metadata(repo_root):
    run = config.load_run_config()
    assert run.analysis_cutoff_date.isoformat() == "2026-09-30"
    assert not run.cutoff_is_year_end
    cff = yaml.safe_load((repo_root / "CITATION.cff").read_text(encoding="utf-8"))
    assert "doi" not in cff                                              # added at the release freeze (D-006)
    assert cff["repository-code"] == "https://github.com/essentia2020/prc-platform-dataset"
