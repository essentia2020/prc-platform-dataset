"""Register-row event map, controlled vocabularies and validator behaviour."""

import copy

import pytest
import yaml

from src.common import register

EVENT_MAP_FIELDS = (
    "launch_year",
    "coverage_start_year",
    "coverage_end_year",
    "data_source",
    "eligibility_events",
    "counting_event",
    "extraction_selector",
    "register_status",
)


@pytest.fixture(scope="module")
def register_data():
    return yaml.safe_load(register.PLATFORMS_YAML.read_text(encoding="utf-8"))


def test_every_row_defines_the_event_map(register_data):
    for row in register_data["platforms"]:
        for name in EVENT_MAP_FIELDS:
            assert name in row, f"{row['row_id']}: missing {name}"
        assert row["data_source"] in ("crossref", "sciety", "both", "none")
        assert row["register_status"] in ("quantified", "register_only")


def test_quantified_rows_have_selector_for_each_source(register_data):
    for row in register_data["platforms"]:
        if row["register_status"] != "quantified":
            continue
        needed = register.SELECTOR_REQUIREMENTS[row["data_source"]]
        assert needed, f"{row['row_id']}: quantified row without a data source"
        for block in needed:
            assert block in row["extraction_selector"], f"{row['row_id']}: missing selector {block}"


def test_rows_pass_validator(register_data):
    register.validate_platforms(register_data["platforms"], register_data["register_meta"])


def test_validator_rejects_unknown_vocabulary(register_data):
    rows = copy.deepcopy(register_data["platforms"])
    rows[0]["initiation_class"] = "editor_initiated"
    with pytest.raises(register.RegisterError, match="initiation_class"):
        register.validate_platforms(rows, register_data["register_meta"])


def test_validator_rejects_missing_event_map_field(register_data):
    rows = copy.deepcopy(register_data["platforms"])
    del rows[0]["counting_event"]
    with pytest.raises(register.RegisterError, match="counting_event"):
        register.validate_platforms(rows, register_data["register_meta"])


def test_validator_rejects_register_only_without_reason(register_data):
    rows = copy.deepcopy(register_data["platforms"])
    rows[0]["register_status"] = "register_only"
    rows[0]["data_status"] = "machine_readable"
    with pytest.raises(register.RegisterError, match="register_only"):
        register.validate_platforms(rows, register_data["register_meta"])


def test_no_binding_decision_field_in_register(register_data):
    for row in register_data["platforms"]:
        assert "binding_publication_decision" not in row, "derived field must not be stored in the register"


def test_qeios_rows_share_organisation_but_differ_in_counting_event(register_data):
    rows = register.platforms_by_row_id(register_data["platforms"])
    hosted, external = rows["qeios_hosted_works"], rows["qeios_external_works"]
    assert hosted["organisation_id"] == external["organisation_id"] == "qeios"
    assert hosted["counting_event"] != external["counting_event"]
    assert hosted["initiation_class"] != external["initiation_class"]


def test_comparators_fail_criterion_one():
    for row in register.load_excluded():
        if row["comparator"]:
            assert row["failed_criterion"] == 1


# ---------------------------------------------------------------- D-069: observed editorial features
def test_observed_editorial_features_are_declared_and_in_vocabulary():
    meta = register.load_yaml(register.PLATFORMS_YAML)["register_meta"]
    rows = register.load_platforms()
    decisions, timings = set(meta["editorial_decision_values"]), set(meta["review_disclosure_timings"])
    assert decisions == {"binary", "none", "unknown"}
    assert timings == {"during_review", "with_acceptance", "none", "unknown"}
    for r in rows:
        assert r["editorial_decision_observed"] in decisions, r["row_id"]
        assert r["review_disclosure_timing"] in timings, r["row_id"]
    by_id = {r["row_id"]: r for r in rows}
    # overlay journal with a binding decision and reports released with the accepted article
    assert by_id["jmirx_med"]["editorial_decision_observed"] == "binary"
    assert by_id["jmirx_med"]["review_disclosure_timing"] == "with_acceptance"
    # public discussion before a binding decision
    assert by_id["copernicus_interactive_public_peer_review"]["editorial_decision_observed"] == "binary"
    assert by_id["copernicus_interactive_public_peer_review"]["review_disclosure_timing"] == "during_review"
    # approval-threshold platform: no editorial decision, reports public as they arrive
    assert by_id["f1000research"]["editorial_decision_observed"] == "none"
    assert "editorial_decision_observed" in register.PLATFORM_COLUMNS
    assert "review_disclosure_timing" in register.PLATFORM_COLUMNS
