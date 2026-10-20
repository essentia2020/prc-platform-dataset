"""Cell-level conventions for every aggregate table.

A *cell* is one (row, year) value.  Its fields are independent:

* ``extraction_status``   — technical state of the scope(s) the row depends on
                            (``complete`` / ``incomplete`` / ``failed``; ``not_applicable``
                            for rows without a machine-readable source);
* ``observation_status``  — ``register_only`` / ``observed`` / ``observed_zero`` /
                            ``not_observable`` / ``not_applicable``;
* ``count``               — integer or empty (``None``);
* ``partial_year``        — True only for the cutoff year when the cutoff is not
                            31 December;
* ``coverage``            — coverage-matrix label.

The rules of docs/analysis_plan.md "Missingness and publication gates" are
implemented here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

OBSERVATION_STATUSES = ("register_only", "observed", "observed_zero", "not_observable", "not_applicable")
COVERAGE_LABELS = ("complete", "year_to_date", "partial_coverage", "partial_known_scope", "no_data", "not_applicable")
ADDITIVITY = ("row_series", "row_summed", "deduplicated")


class AggregateError(ValueError):
    pass


@dataclass(frozen=True)
class Cell:
    row_id: str
    year: int
    count: int | None
    observation_status: str
    extraction_status: str
    partial_year: bool
    coverage: str
    source_observability_status: str = "observable"


def is_partial_year(year: int, cutoff: date) -> bool:
    return year == cutoff.year and not (cutoff.month == 12 and cutoff.day == 31)


def year_label(year: int, cutoff: date) -> str:
    return f"{year} (year_to_date, cutoff {cutoff.isoformat()})" if is_partial_year(year, cutoff) else str(year)


def cell_for(*, row_id: str, year: int, cutoff: date, register_status: str, extraction_status: str,
             source_observable: bool, in_eligible_range: bool, data_status: str, n_works: int | None,
             partial_known_scope: bool = False) -> Cell:
    """Derive one cell from independent inputs; ``n_works`` is ignored unless publishable."""
    partial = is_partial_year(year, cutoff)
    if register_status == "register_only":
        return Cell(row_id, year, None, "register_only", extraction_status, partial, "not_applicable",
                    "observable" if source_observable else "not_observable")
    if not in_eligible_range:
        return Cell(row_id, year, None, "not_applicable", extraction_status, partial, "not_applicable")
    if extraction_status != "complete":
        # An incomplete or failed walk never yields a number — not even zero.
        return Cell(row_id, year, None, "not_observable", extraction_status, partial, "no_data")
    if not source_observable:
        # Completed extraction but the source cannot observe this row/year:
        # not_observable takes priority over observed_zero.
        return Cell(row_id, year, None, "not_observable", extraction_status, partial, "no_data", "not_observable")
    if n_works is None:
        raise AggregateError(f"{row_id}/{year}: complete extraction without a computed count")
    coverage = "year_to_date" if partial else ("partial_coverage" if data_status == "partial_coverage" else "complete")
    if partial_known_scope:
        coverage = "partial_known_scope"
    status = "observed_zero" if n_works == 0 else "observed"
    return Cell(row_id, year, int(n_works), status, extraction_status, partial, coverage,
                "partial_known_scope" if partial_known_scope else "observable")


def headline_rows(rows: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Rows eligible for configuration- and class-stratified aggregates.

    Provisional rows and register-only rows are excluded; they stay in the
    register summary and the coverage matrix.
    """
    return [r for r in rows if not r.get("provisional") and r.get("register_status") == "quantified"]


def sum_row_series(cells: Iterable[Cell]) -> int | None:
    """``row_summed`` additivity: empty if any contributing cell is empty."""
    total = 0
    for cell in cells:
        if cell.count is None:
            return None
        total += cell.count
    return total


def check_no_group_total(table_name: str, additivity: str, group_columns: Iterable[str]) -> None:
    """Guard: class/configuration tables never carry an all-rows total line."""
    if additivity not in ADDITIVITY:
        raise AggregateError(f"{table_name}: unknown additivity {additivity!r}")
    if additivity == "row_summed" and not list(group_columns):
        raise AggregateError(f"{table_name}: row_summed tables need a grouping column; an all-row total "
                             "is only published deduplicated in unique_works_all_rows_year.csv")
