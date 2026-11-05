"""Synthetic, offline checks of the read-only early-year reconciliation."""
import gzip
import hashlib
import json

import pytest

from src.common.raw_store import RawStore
from src.common.register import load_platforms
from src.extract.selectors import crossref_selectors
from tools.check_f1000_early_years import (
    compare, population, pooled_2012_summary, raw_records, reconcile_year, walk_paths,
)


def record(doi, issued, flag="", title="Synthetic article"):
    return dict(row_entity_type="work_record", canonical_work_id="doi:synthetic",
                source_record_id=doi, work_doi=doi, issued=issued, event_date_raw=issued,
                record_flag=flag, exclusion_reason="", title=title)


def work(year, *, included="true", in_range="true"):
    return dict(included=included, in_eligible_range=in_range, counting_year=year,
                exclusion_reason="", counting_record_id="v2", counting_event_date_raw=year,
                date_order_ambiguous="false", tie_break_source="")


def test_reconciliation_keeps_withdrawn_record_and_selected_event_visible():
    records = [record("v1", "2012-04-01", "withdrawn", "WITHDRAWN"),
               record("v2", "2013-02-01")]
    result = reconcile_year(records, {"doi:synthetic": work("2013")}, 2012)
    assert result["record_lines"] == result["distinct_canonical_work_ids"] == 1
    exception, = result["exceptions"]
    assert exception["work"]["counting_year"] == "2013"
    assert exception["records"][0]["record_flag"] == "withdrawn"
    assert exception["counted"]


def test_record_year_is_not_a_work_year_and_missing_work_is_explicit():
    records = [record("v1", "2012-04-01"), record("v2", "2013-02-01")]
    result = reconcile_year(records, {"doi:synthetic": work("2012", in_range="false")}, 2013)
    assert result["exceptions"][0]["work"]["counting_year"] == "2012"
    assert not result["exceptions"][0]["counted"]
    assert reconcile_year(records, {}, 2012)["outcomes"] == {"missing_work_row": 1}


def test_evaluation_blank_ids_do_not_create_an_extra_work():
    records = [record("v1", "2012"), dict(record("review", "2012"),
               row_entity_type="evaluation_record", canonical_work_id="")]
    result = reconcile_year(records, {"doi:synthetic": work("2012", in_range="false")}, 2012)
    assert result["all_record_lines"] == 2
    assert result["record_lines_by_entity_type"] == {"evaluation_record": 1, "work_record": 1}
    assert result["distinct_ids_including_blank_all_records"] == 2
    assert result["blank_canonical_id_lines"] == 1
    assert result["record_lines"] == result["distinct_canonical_work_ids"] == 1


def test_population_and_comparison_distinguish_duplicates_versions_and_missing_dois():
    platform = next(r for r in load_platforms() if r["row_id"] == "f1000research")
    pattern = platform["doi_version_pattern"]
    a = dict(doi="10.12688/f1000research.1-1.v1", issued="2012")
    b = dict(doi="10.12688/f1000research.1-1.v2", issued="2012")
    c = dict(doi="10.12688/f1000research.1-2.v1", issued="2012")
    raw = [a, a, b, c]
    assert population(raw, pattern) == {
        "record_lines": 4, "distinct_dois": 3, "distinct_canonical_work_ids": 2}
    interim = [a, dict(b, issued="2013")]
    result = compare(raw, interim, [record(a["doi"], "2012")], pattern)
    assert result["raw_2012_duplicate_dois"] == {a["doi"]: 2}
    assert result["raw_2012_not_in_interim_any_year"] == [c["doi"]]
    assert result["raw_2012_in_interim_but_not_issued_2012"] == [b["doi"]]
    assert not result["interim_2012_not_in_processed_2012"]


def test_comparison_uses_version_dois_not_processed_canonical_stems():
    platform = next(r for r in load_platforms() if r["row_id"] == "f1000research")
    pattern = platform["doi_version_pattern"]
    stem = "10.12688/f1000research.1-19"
    interim = [dict(doi=f"{stem}.v{n}", issued="2012") for n in (1, 2)]
    records = [dict(record(r["doi"], "2012"), work_doi=stem,
                    canonical_work_id=f"doi:{stem}") for r in interim]
    matched = compare(interim, interim, records, pattern)
    assert matched["interim_2012_not_in_processed_2012"] == []
    assert matched["processed_2012_not_in_interim_2012"] == []
    # A missing version must remain visible even if the canonical work is present.
    missing = compare(interim, interim, records[:1], pattern)
    assert missing["interim_2012_not_in_processed_2012"] == [f"{stem}.v2"]
    extra = compare(interim, interim[:1], records, pattern)
    assert extra["processed_2012_not_in_interim_2012"] == [f"{stem}.v2"]


def test_four_trace_paths_include_20261027_without_repeating_selected_manifest(tmp_path):
    paths = walk_paths(tmp_path, "run_20261102_01", "w01")
    assert len(paths) == 4
    assert [p.parent.name for _, p in paths] == [
        "run_20261102_01", "run_20261026_01", "run_20261026_01", "run_20261027_01"]
    assert paths[-1][1].name.endswith("__w01.manifest.jsonl")
    assert len(walk_paths(tmp_path, "run_20261027_01", "w01")) == 3


def test_pooled_check_verifies_doi_identity_not_just_equal_counts():
    pattern = next(r for r in load_platforms() if r["row_id"] == "f1000research")["doi_version_pattern"]
    a = dict(doi="10.12688/f1000research.1-19.v1", issued="2012")
    b = dict(doi="10.12688/f1000research.1-19.v2", issued="2012")
    traces = {label: [a, b] for label in ("selected", "old1", "old2", "old3")}
    matched = pooled_2012_summary(traces, pattern)
    assert matched["matches_four_copies_of_selected"]
    assert matched["pooled"] == {
        "record_lines": 8, "distinct_dois": 2, "distinct_canonical_work_ids": 1}
    assert matched["doi_occurrence_histogram"] == {4: 2}
    different = dict(traces, old3=[a, dict(b, doi="10.12688/f1000research.1-20.v1")])
    assert not pooled_2012_summary(different, pattern)["matches_four_copies_of_selected"]
    assert not pooled_2012_summary(dict(list(traces.items())[:3]), pattern)["matches_four_copies_of_selected"]
    assert not pooled_2012_summary({k: [a, a] for k in traces}, pattern)["matches_four_copies_of_selected"]


@pytest.mark.parametrize("state", ["complete", "failed"])
def test_raw_check_reads_only_accepted_pages_and_reports_state(tmp_path, state):
    payload = {"message": {"items": [
        {"DOI": "10.12688/f1000research.1-1.v1", "type": "journal-article",
         "issued": {"date-parts": [[2012, 7, 1]]}},
        {"DOI": "10.12688/another.1", "type": "journal-article",
         "issued": {"date-parts": [[2012]]}},
    ]}}
    data = gzip.compress(json.dumps(payload).encode())
    (tmp_path / "accepted.json.gz").write_bytes(data)
    entries = [
        dict(record="walk_header", run_id="run_test", walk_id="w01", source="crossref", scope="test"),
        dict(record="rejected_attempt", response_path="absent_rejected.json.gz"),
        dict(record="page", page=1, accepted_attempt=2, response_path="accepted.json.gz",
             sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), http_status=200, items_in_page=2),
        dict(record="walk_end", walk_state=state),
    ]
    manifest = tmp_path / "walk.jsonl"
    manifest.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    platform = next(r for r in load_platforms() if r["row_id"] == "f1000research")
    selector, = crossref_selectors([platform])
    walk, records = raw_records(manifest, RawStore(tmp_path), selector)
    assert walk.state == state
    assert records == [dict(doi="10.12688/f1000research.1-1.v1", issued="2012-07-01",
                            page=1, accepted_attempt=2)]
    (tmp_path / "accepted.json.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        raw_records(manifest, RawStore(tmp_path), selector)
