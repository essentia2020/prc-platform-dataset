"""Boundary tests 1, 2 and 4: cutoff logic and year-only dates."""

from __future__ import annotations

from datetime import date

import pytest

from src.common.dates import (DateError, cutoff_status, format_partial_date, interval_hull,
                              parse_crossref_date, parse_partial_date)

CUTOFF = date(2026, 9, 30)


@pytest.mark.parametrize("value, expected", [
    ("2026-09-30", "included"),      # on the cutoff day
    ("2026-10-01", "future"),        # the day after
    ("2026-09", "included"),         # month ends on the cutoff day
    ("2026-10", "future"),           # month starts after the cutoff
    ("2026", "ambiguous_cutoff_date"),  # year straddles the cutoff
    ("2025", "included"),
    ("2027", "future"),
    (None, "missing_event_date"),
    ("", "missing_event_date"),
])
def test_cutoff_rule(value, expected):
    assert cutoff_status(parse_partial_date(value), CUTOFF) == expected


def test_year_end_cutoff_makes_year_only_dates_unambiguous():
    assert cutoff_status(parse_partial_date("2025"), date(2025, 12, 31)) == "included"
    assert cutoff_status(parse_partial_date("2026"), date(2025, 12, 31)) == "future"


def test_year_only_date_is_an_interval_not_a_point():
    interval = parse_partial_date("2024")
    assert (interval.start, interval.end, interval.precision) == (date(2024, 1, 1), date(2024, 12, 31), "year")
    assert interval.year == 2024
    assert format_partial_date(interval) == "2024"


def test_month_precision_uses_last_day_of_month():
    assert parse_partial_date("2024-02").end == date(2024, 2, 29)
    assert parse_partial_date("2023-02").end == date(2023, 2, 28)


def test_crossref_date_parts_precision():
    assert parse_crossref_date({"date-parts": [[2024, 3]]}).precision == "month"
    assert parse_crossref_date({"date-parts": [[2024]]}).precision == "year"
    assert parse_crossref_date({"date-parts": [[2024, 3, 11]]}).precision == "day"
    assert parse_crossref_date({"date-parts": [[None]]}) is None
    assert parse_crossref_date({}) is None


def test_no_imputation_for_invalid_values():
    with pytest.raises(DateError):
        parse_partial_date("2024-13")
    with pytest.raises(DateError):
        parse_partial_date("March 2024")


def test_timestamp_values_are_reduced_to_their_day():
    interval = parse_partial_date("2024-03-11T10:00:00.000Z")
    assert interval.precision == "day" and interval.raw == "2024-03-11"


def test_derived_interval_is_conservative_and_unasserted():
    hull = interval_hull([parse_partial_date("2024-03-11"), parse_partial_date("2024")])
    assert (hull.start, hull.end, hull.precision, hull.raw) == (date(2024, 1, 1), date(2024, 12, 31), "year", "")
