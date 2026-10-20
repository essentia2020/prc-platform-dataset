"""Partial dates, closed calendar intervals and the cutoff rule.

Sources assert dates at day, month or year precision.  Every asserted date
is represented as a closed interval ``[start, end]`` on the calendar:

* ``2024-03-11`` -> ``[2024-03-11, 2024-03-11]`` (precision ``day``)
* ``2024-03``    -> ``[2024-03-01, 2024-03-31]`` (precision ``month``)
* ``2024``       -> ``[2024-01-01, 2024-12-31]`` (precision ``year``)

The cutoff rule compares the interval with ``analysis_cutoff_date``:

* ``included``               when ``end <= cutoff``
* ``future``                 when ``start > cutoff``
* ``ambiguous_cutoff_date``  when ``start <= cutoff < end``
* ``missing_event_date``     when no interval exists

No date value is ever imputed; a missing date stays missing.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime

PRECISIONS = ("day", "month", "year")
CUTOFF_STATUSES = ("included", "future", "ambiguous_cutoff_date", "missing_event_date")

_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR = re.compile(r"^(\d{4})$")


class DateError(ValueError):
    """Raised when a date value cannot be interpreted."""


@dataclass(frozen=True)
class DateInterval:
    start: date
    end: date
    precision: str
    raw: str

    @property
    def year(self) -> int:
        return self.end.year

    def as_row(self, prefix: str) -> dict[str, str]:
        """Columns ``<prefix>_date_raw`` … ``<prefix>_interval_end``."""
        return {
            f"{prefix}_date_raw": self.raw,
            f"{prefix}_date_precision": self.precision,
            f"{prefix}_interval_start": self.start.isoformat(),
            f"{prefix}_interval_end": self.end.isoformat(),
        }


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def interval_from_parts(year: int, month: int | None = None, day: int | None = None,
                        raw: str | None = None) -> DateInterval:
    """Build an interval from numeric parts (Crossref ``date-parts`` style)."""
    if month is None:
        text = raw if raw is not None else f"{year:04d}"
        return DateInterval(date(year, 1, 1), date(year, 12, 31), "year", text)
    if day is None:
        text = raw if raw is not None else f"{year:04d}-{month:02d}"
        return DateInterval(date(year, month, 1), _month_end(year, month), "month", text)
    text = raw if raw is not None else f"{year:04d}-{month:02d}-{day:02d}"
    point = date(year, month, day)
    return DateInterval(point, point, "day", text)


def parse_partial_date(value: object) -> DateInterval | None:
    """Parse ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD`` or an ISO timestamp.

    Returns ``None`` for empty values.  Raises :class:`DateError` for values
    that look like dates but are not valid calendar dates.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _DAY.match(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        try:
            return interval_from_parts(year, month, day, raw=text[:10])
        except ValueError as exc:  # pragma: no cover - defensive
            raise DateError(f"invalid day date {text!r}") from exc
    match = _MONTH.match(text)
    if match:
        year, month = (int(g) for g in match.groups())
        if not 1 <= month <= 12:
            raise DateError(f"invalid month date {text!r}")
        return interval_from_parts(year, month, raw=text)
    match = _YEAR.match(text)
    if match:
        return interval_from_parts(int(match.group(1)), raw=text)
    raise DateError(f"unrecognised date value {text!r}")


def parse_crossref_date(field: object) -> DateInterval | None:
    """Parse a Crossref date object (``{"date-parts": [[y, m, d]]}``).

    ``date-parts`` with ``None`` elements or an empty list yield ``None``.
    """
    if not isinstance(field, dict):
        return None
    parts = field.get("date-parts")
    if not parts or not isinstance(parts, list) or not parts[0]:
        return None
    first = [p for p in parts[0] if p is not None]
    if not first:
        return None
    try:
        year = int(first[0])
        month = int(first[1]) if len(first) > 1 else None
        day = int(first[2]) if len(first) > 2 else None
        return interval_from_parts(year, month, day)
    except (TypeError, ValueError) as exc:
        raise DateError(f"invalid Crossref date-parts {parts!r}") from exc


def format_partial_date(interval: DateInterval | None) -> str:
    """Interim-layer representation (``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``)."""
    if interval is None:
        return ""
    if interval.precision == "year":
        return f"{interval.start.year:04d}"
    if interval.precision == "month":
        return f"{interval.start.year:04d}-{interval.start.month:02d}"
    return interval.start.isoformat()


def parse_timestamp(value: object) -> str:
    """Pass a ``date-time`` string through unchanged after validation."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DateError(f"invalid timestamp {text!r}") from exc
    return text


def cutoff_status(interval: DateInterval | None, cutoff: date) -> str:
    """Apply the cutoff rule to one interval (see module docstring)."""
    if interval is None:
        return "missing_event_date"
    if interval.end <= cutoff:
        return "included"
    if interval.start > cutoff:
        return "future"
    return "ambiguous_cutoff_date"


def interval_hull(intervals: list[DateInterval]) -> DateInterval:
    """Conservative hull of several intervals (earliest start, latest end).

    Used only for *derived* intervals; the result carries precision ``year``
    if any input is year-precision, else ``month`` if any is month-precision,
    else ``day``.  ``raw`` is empty because no single source asserted it.
    """
    if not intervals:
        raise DateError("interval_hull of an empty list")
    start = min(i.start for i in intervals)
    end = max(i.end for i in intervals)
    ranks = {p: n for n, p in enumerate(PRECISIONS)}
    precision = max((i.precision for i in intervals), key=lambda p: ranks[p])
    return DateInterval(start, end, precision, "")


def intervals_overlap(a: DateInterval, b: DateInterval) -> bool:
    return a.start <= b.end and b.start <= a.end
