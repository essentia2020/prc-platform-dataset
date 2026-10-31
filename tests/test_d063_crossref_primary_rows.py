"""D-063 / D-064: The Unjournal and MetaROR counted from Crossref peer-review records.

Selector behaviour on the real DOI shapes observed on 2026-10-31, the fixture
run (one work per reviewed target, placeholder target creates no work) and
the register prefix check for members 51568 (RoRI) and 9621 (PubPub).
"""
from __future__ import annotations

import json

import pytest

from src.common.register import load_platforms, platforms_by_row_id
from src.extract.selectors import PLACEHOLDER_TARGET_RE, compile_crossref_selector, review_targets
from tests.offline import FixtureTransport, run_full_pipeline
from tools import check_register_prefixes as prefix_check


def _record(doi, record_type, target=None, container=None):
    item = {"DOI": doi, "type": record_type, "prefix": doi.split("/")[0]}
    if container:
        item["container-title"] = [container]
    if target:
        item["relation"] = {"is-review-of": [{"id": target, "id-type": "doi", "asserted-by": "subject"}]}
    return item


@pytest.fixture(scope="module")
def selectors():
    rows = platforms_by_row_id(load_platforms())
    return rows, compile_crossref_selector(rows["metaror"]), compile_crossref_selector(rows["the_unjournal"])


# ------------------------------------------------------------------ register
def test_register_rows_are_crossref_primary_with_sciety_cross_check(selectors):
    rows, metaror, unjournal = selectors
    for row_id in ("metaror", "the_unjournal"):
        row = rows[row_id]
        assert row["data_source"] == "both"
        assert row["extraction_selector"]["crossref"]["role"] == "primary"
        assert row["extraction_selector"]["sciety"]["role"] == "cross_check"
        assert row["extraction_selector"]["crossref"]["record_types"] == ["peer-review"]
        assert row["extraction_selector"]["crossref"]["target_filter"] == "external"
        assert row["review_to_object_relation"] == "crossref_is_review_of"
        assert row["counting_event"] == "earliest_qualifying_evaluation"
        assert row["counting_event_date_field"] == "issued"
    assert rows["metaror"]["data_status"] == "machine_readable"
    assert rows["the_unjournal"]["data_status"] == "partial_coverage"
    assert "d28e8e57" in rows["the_unjournal"]["model_note"]
    assert list(metaror.prefixes) == ["10.70744"] and list(unjournal.prefixes) == ["10.21428"]


# ----------------------------------------------------------------- selectors
def test_metaror_review_shapes_are_claimed_and_hosted_content_is_not(selectors):
    _, metaror, _ = selectors
    claimed = [_record("10.70744/metaror.9.1.rv3", "peer-review", "10.31235/osf.io/b2ra3"),
               _record("10.70744/metaror.43.1.ea", "peer-review", "10.31219/osf.io/s4vc5"),
               _record("10.70744/MetaROR.12.2.rv10", "peer-review", "10.64898/example1")]
    for item in claimed:
        assert metaror.claims_review(item, review_targets(item)), item["DOI"]
    # the posted-content record under 10.70744 is outside record_types: never a review, never a work
    posted = _record("10.70744/metaror.77.1", "posted-content")
    assert not metaror.claims_review(posted, review_targets(posted))
    assert not metaror.matches_work(posted)
    # D-064: the stem is the selector; a peer-review under the prefix outside the stem is not claimed
    assert metaror.review_doi_regex.pattern == r"^10\.70744/metaror\."
    odd = _record("10.70744/rori.2025.1", "peer-review", "10.31219/osf.io/zzzzz")
    assert not metaror.claims_review(odd, review_targets(odd))


def test_unjournal_stem_is_the_selector_under_the_shared_pubpub_prefix(selectors):
    _, _, unjournal = selectors
    item = _record("10.21428/d28e8e57.652a843a", "peer-review", "10.3386/w26775", container="The Unjournal")
    assert unjournal.claims_review(item, review_targets(item))
    # journal-article summary without a relation and component records under the stem are never selected
    summary = _record("10.21428/d28e8e57.ad95c497", "journal-article", container="The Unjournal")
    component = _record("10.21428/d28e8e57.ad95c497/release/1", "component")
    for rec in (summary, component):
        assert not unjournal.claims_review(rec, review_targets(rec)), rec["DOI"]
        assert not unjournal.matches_work(rec), rec["DOI"]
    # another PubPub community's review with an external target is not the Unjournal's
    other = _record("10.21428/0f1e2d3c.aaaa0001", "peer-review", "10.1101/2024.01.01.999999")
    assert not unjournal.claims_review(other, review_targets(other))
    # container-title is not the selector: a stem review without one is still claimed
    bare = _record("10.21428/d28e8e57.bbbb0002", "peer-review", "10.2139/ssrn.4000000")
    assert bare.get("container-title") is None and unjournal.claims_review(bare, review_targets(bare))


@pytest.mark.parametrize("target", ["10.70744/MetaROR.placeholder01", "10.70744/metaror.placeholder01",
                                    "10.70744/METAROR.PLACEHOLDER01", "10.1234/placeholder"])
def test_operator_placeholder_target_is_flagged_case_insensitively(selectors, target):
    _, metaror, _ = selectors
    assert PLACEHOLDER_TARGET_RE.match(target)
    item = _record("10.70744/metaror.282.1.rv1", "peer-review", target)
    (t,) = review_targets(item)
    assert t.flag == "placeholder"
    # the review record is still the row's (its DOI shape says so); the flag decides at normalise time
    assert metaror.claims_review(item, review_targets(item))


@pytest.mark.parametrize("doi", ["10.70744/metaror.9.1", "10.31235/osf.io/b2ra3", "10.3386/w26775",
                                 "10.1101/2024.01.01.000001", "10.21428/d28e8e57.652a843a"])
def test_real_targets_are_not_mistaken_for_placeholders(doi):
    assert not PLACEHOLDER_TARGET_RE.match(doi)


# --------------------------------------------------------------- fixture run
@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    return run_full_pipeline(tmp_path_factory.mktemp("d063"), transport=FixtureTransport(scripted={}))


def test_several_reviews_of_one_work_give_one_work_at_the_earliest_review(outputs):
    # MetaROR fixture: rv3 (2025-01-10) and ea (2025-02-01) of the same preprint, rv1 of another in 2024,
    # plus one review whose target is the placeholder DOI
    assert outputs.cell("works_by_row_year", row_id="metaror", year=2024)["count"] == "1"
    assert outputs.cell("works_by_row_year", row_id="metaror", year=2025)["count"] == "1"
    cell_2026 = outputs.cell("works_by_row_year", row_id="metaror", year=2026)
    assert cell_2026["count"] == "0" and cell_2026["observation_status"] == "observed_zero"
    # The Unjournal fixture: two stem reviews of 10.3386/w26775 in 2023, one of another work in 2024,
    # one review of another PubPub community (not counted)
    assert outputs.cell("works_by_row_year", row_id="the_unjournal", year=2023)["count"] == "1"
    assert outputs.cell("works_by_row_year", row_id="the_unjournal", year=2024)["count"] == "1"
    for year in (2023, 2024, 2025, 2026):
        assert outputs.cell("works_by_row_year", row_id="the_unjournal", year=year)["coverage"] == "partial_coverage"
    assert not [r for r in outputs.records("the_unjournal") if "0f1e2d3c" in r["source_record_id"]]
    assert {w["canonical_work_id"] for w in outputs.works("the_unjournal")} == {
        "doi:10.3386/w26775", "doi:10.1016/j.jdeveco.2024.103000"}


def test_placeholder_target_is_kept_as_flagged_record_and_creates_no_work(outputs):
    records = outputs.records("metaror")
    flagged = [r for r in records if r["record_flag"] == "placeholder_target"]
    assert len(flagged) == 1 and flagged[0]["evaluation_doi"] == "10.70744/metaror.282.1.rv1"
    assert flagged[0]["reviewed_work_id"] == "id:crossref:10.70744/MetaROR.placeholder01"
    works = {w["canonical_work_id"] for w in outputs.works("metaror")}
    assert works == {"doi:10.31219/osf.io/abcde", "doi:10.1101/2024.05.01.000001"}
    # D-064: the affected records are counted in the data-quality log as a run row of the metaror row
    from src.common.interim import read_csv
    dq = [r for r in read_csv(outputs.processed / "data_quality_log.csv")
          if r["row_id"] == "metaror" and r["issue_type"] == "placeholder_relation"]
    assert len(dq) == 1 and dq[0]["origin"] == "run" and dq[0]["n_records_affected"] == "1"
    assert dq[0]["walk_id"].startswith("crossref/works__10.70744__peer-review=")


def test_rows_join_their_groups_as_observable_members(outputs):
    author = outputs.cell("unique_works_by_class_year", initiation_class="author_initiated", year=2025)
    assert "metaror" not in author["excluded_rows"] and "metaror" not in author["blocking_rows"]
    mixed = outputs.cell("unique_works_by_class_year", initiation_class="mixed", year=2024)
    assert "the_unjournal:partial_coverage" in mixed["lower_bound_rows"]
    assert "the_unjournal" not in mixed["excluded_rows"]
    summary = {r["row_id"]: r for r in outputs.table("register_summary")}
    assert summary["metaror"]["unique_works_to_cutoff"] == "2"
    assert summary["the_unjournal"]["unique_works_to_cutoff"] == "2"


# ------------------------------------------------------------ prefix check
class _Resolver:
    def __init__(self, records):
        self.records, self.urls = records, []

    def __call__(self, url, headers, timeout):
        from urllib.parse import unquote
        self.urls.append(url)
        doi = unquote(url.split("/works/", 1)[1].split("?", 1)[0]).lower()
        rec = self.records.get(doi)
        if rec is None:
            return 404, {}, b"Resource not found."
        return 200, {}, json.dumps({"status": "ok", "message": rec}).encode()


def test_prefix_check_expectations_for_members_51568_and_9621():
    rows = load_platforms()
    records = {"10.70744/metaror.9.1.rv3": {"prefix": "10.70744", "member": "51568", "type": "peer-review"},
               "10.21428/d28e8e57.652a843a": {"prefix": "10.21428", "member": "9621", "type": "peer-review"}}
    results = prefix_check.run_check(rows, _Resolver(records), base_url="https://api.crossref.org",
                                     mailto="x@example.org", user_agent="t/1", only={"metaror", "the_unjournal"},
                                     sleep=lambda s: None)
    by_row = {r.row_id: r for r in results}
    assert set(by_row) == {"metaror", "the_unjournal"} and {r.status for r in by_row.values()} == {"ok"}
    for row_id, member, prefix in (("metaror", "51568", "10.70744"), ("the_unjournal", "9621", "10.21428")):
        checks = {c.role: c for c in by_row[row_id].checks}
        assert checks["review"].status == "ok" and checks["review"].member == member
        assert checks["review"].owner_prefix == prefix and prefix in checks["review"].declared
        assert checks["work"].status == "not_applicable"       # works are the external targets
    assert prefix_check.exit_code(results) == 0
