"""§9.10 conventions: blanks vs zeros, not_observable priority, partial year, provisional exclusion,
Qeios zero intersection, Gates/VeriXiv overlap, additivity (boundary tests 4-6 at cell level)."""

from __future__ import annotations

from datetime import date

import pytest

from src.common.aggregates import (AggregateError, Cell, cell_for, check_no_group_total, headline_rows,
                                   is_partial_year, sum_row_series, year_label)
from src.common.register import load_platforms, platforms_by_row_id
from src.extract.selectors import compile_crossref_selector, review_targets

CUTOFF = date(2026, 9, 30)


def _cell(**kw) -> Cell:
    base = dict(row_id="r", year=2024, cutoff=CUTOFF, register_status="quantified", extraction_status="complete",
                source_observable=True, in_eligible_range=True, data_status="machine_readable", n_works=3)
    base.update(kw)
    return cell_for(**base)


def test_register_only_rows_publish_blank_cells():
    cell = _cell(register_status="register_only", n_works=None)
    assert cell.count is None and cell.observation_status == "register_only" and cell.coverage == "not_applicable"


def test_complete_extraction_with_empty_result_is_zero():
    cell = _cell(n_works=0)
    assert cell.count == 0 and cell.observation_status == "observed_zero" and cell.coverage == "complete"


def test_incomplete_or_failed_extraction_never_yields_a_number():
    for state in ("incomplete", "failed"):
        cell = _cell(extraction_status=state, n_works=0)
        assert cell.count is None and cell.observation_status == "not_observable" and cell.coverage == "no_data"


def test_not_observable_takes_priority_over_zero():
    cell = _cell(source_observable=False, n_works=0)
    assert cell.count is None and cell.observation_status == "not_observable"
    assert cell.source_observability_status == "not_observable"


def test_complete_extraction_without_a_count_is_an_error():
    with pytest.raises(AggregateError):
        _cell(n_works=None)


def test_partial_year_labelling():
    assert is_partial_year(2026, CUTOFF) and not is_partial_year(2025, CUTOFF)
    assert not is_partial_year(2026, date(2026, 12, 31))
    assert year_label(2026, CUTOFF) == "2026 (year_to_date, cutoff 2026-09-30)"
    assert year_label(2025, CUTOFF) == "2025"
    cell = _cell(year=2026)
    assert cell.partial_year and cell.coverage == "year_to_date"


def test_partial_coverage_rows_are_labelled_in_full_years():
    assert _cell(data_status="partial_coverage").coverage == "partial_coverage"


def test_provisional_rows_leave_headline_tables_but_stay_in_register():
    rows = load_platforms()
    kept = {r["row_id"] for r in headline_rows(rows)}
    provisional = {r["row_id"] for r in rows if r["provisional"]}
    register_only = {r["row_id"] for r in rows if r["register_status"] == "register_only"}
    assert provisional and provisional.isdisjoint(kept)
    assert register_only.isdisjoint(kept)
    assert "verixiv" in provisional


def test_row_summed_additivity_propagates_blanks():
    cells = [_cell(), _cell(row_id="s", extraction_status="failed", n_works=None)]
    assert sum_row_series(cells) is None
    assert sum_row_series([_cell(), _cell(row_id="s", n_works=0)]) == 3


def test_no_all_row_total_in_group_tables():
    check_no_group_total("works_by_class_year.csv", "row_summed", ["initiation_class"])
    with pytest.raises(AggregateError):
        check_no_group_total("works_by_class_year.csv", "row_summed", [])
    with pytest.raises(AggregateError):
        check_no_group_total("x.csv", "grand_total", ["a"])


# ------------------------------------------------------------- Qeios / Gates
def _review(doi, target):
    return {"DOI": doi, "type": "peer-review", "relation": {"is-review-of": [{"id": target, "id-type": "doi"}]}}


def test_qeios_rows_have_zero_intersection_by_construction():
    rows = platforms_by_row_id(load_platforms())
    hosted = compile_crossref_selector(rows["qeios_hosted_works"])
    external = compile_crossref_selector(rows["qeios_external_works"])
    samples = [_review("10.32388/r1", "10.32388/abc"), _review("10.32388/r2", "10.1101/2024.01.01.000001"),
               _review("10.32388/r3", "10.32388/ABC.3"), _review("10.32388/r4", "10.1234/placeholder")]
    for item in samples:
        targets = review_targets(item)
        assert not (hosted.claims_review(item, targets) and external.claims_review(item, targets)), item["DOI"]
    assert hosted.claims_review(samples[0], review_targets(samples[0]))
    assert external.claims_review(samples[1], review_targets(samples[1]))
    assert not external.doi_in_scope("10.1101/x")   # the external row never owns work records


def test_gates_and_verixiv_overlap_is_expected_not_an_error():
    rows = platforms_by_row_id(load_platforms())
    gates, verixiv = rows["gates_open_research"], rows["verixiv"]
    assert gates["organisation_id"] == verixiv["organisation_id"] == "gates_f1000"
    assert gates["counting_event"] != verixiv["counting_event"] or gates["doi_pattern"] != verixiv["doi_pattern"]
    # the overlap table design: works present in more than one row are reported, not removed
    assert any("overlap" in str(verixiv.get(k, "")).lower() for k in ("model_note", "configuration_note", "classification_note"))
