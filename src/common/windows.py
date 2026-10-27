"""Date windows for windowed cursor walks (D-045 option c, D-057).

A scope whose single cursor walk loses records between cursor steps is walked
as a set of date windows instead.  Each window is an ordinary cursor walk of
its own sub-scope at tolerance 0; the window set is built here so that it
partitions the whole date axis by construction:

* a leading guard window ``until <first_window_start − 1 day>``;
* consecutive calendar periods (``quarter``, ``month`` or ``year``) from
  ``first_window_start`` through the period containing the analysis cutoff;
* a trailing guard window ``from <end of last period + 1 day>`` without an
  upper bound.

Crossref's ``from-*-date`` / ``until-*-date`` filters are inclusive at both
ends, so adjacent windows are disjoint and leave no day uncovered.  Records
without a value for the window field fall outside every window; the
windowed walker detects that through the probe of the unwindowed total.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

GRANULARITIES = ("quarter", "month", "year")

# Register field name -> Crossref filter stem (``from-<stem>-date`` / ``until-<stem>-date``).
DATE_FILTER_STEMS = {
    "issued": "issued",
    "created": "created",
    "deposited": "deposit",
    "posted": "posted",
    "published": "pub",
    "indexed": "index",
}


class WindowError(ValueError):
    """Raised for a window configuration that cannot partition the axis."""


@dataclass(frozen=True)
class DateWindow:
    date_field: str
    start: date | None      # None -> open lower bound (leading guard)
    end: date | None        # None -> open upper bound (trailing guard)

    @property
    def label(self) -> str:
        lo = self.start.isoformat() if self.start else "min"
        hi = self.end.isoformat() if self.end else "max"
        return f"{self.date_field}_{lo}_{hi}"

    @property
    def crossref_filter(self) -> str:
        stem = DATE_FILTER_STEMS[self.date_field]
        parts = []
        if self.start is not None:
            parts.append(f"from-{stem}-date:{self.start.isoformat()}")
        if self.end is not None:
            parts.append(f"until-{stem}-date:{self.end.isoformat()}")
        return ",".join(parts)

    def as_record(self) -> dict:
        return {"label": self.label, "date_field": self.date_field,
                "from": self.start.isoformat() if self.start else None,
                "until": self.end.isoformat() if self.end else None}


def window_scope_id(scope_id: str, window: DateWindow) -> str:
    """Sub-scope id of one window: ``<scope_id>__<field>_<from>_<until>``."""
    return f"{scope_id}__{window.label}"


def _period_start(day: date, granularity: str) -> date:
    if granularity == "year":
        return date(day.year, 1, 1)
    if granularity == "quarter":
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    return date(day.year, day.month, 1)


def _period_end(start: date, granularity: str) -> date:
    if granularity == "year":
        return date(start.year, 12, 31)
    if granularity == "quarter":
        month = start.month + 2
        return date(start.year, month, calendar.monthrange(start.year, month)[1])
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def date_windows(date_field: str, granularity: str, first_window_start: date, through: date) -> list[DateWindow]:
    """Guard + periods + guard, covering every day of the axis exactly once.

    ``through`` is the last day that must fall inside a bounded period
    (normally the analysis cutoff); the trailing guard starts the day after
    the period that contains it.
    """
    if date_field not in DATE_FILTER_STEMS:
        raise WindowError(f"unknown window date_field {date_field!r}; known: {sorted(DATE_FILTER_STEMS)}")
    if granularity not in GRANULARITIES:
        raise WindowError(f"unknown window granularity {granularity!r}; known: {GRANULARITIES}")
    if _period_start(first_window_start, granularity) != first_window_start:
        raise WindowError(f"first_window_start {first_window_start} is not the first day of a {granularity}")
    if through < first_window_start:
        raise WindowError(f"cutoff {through} lies before first_window_start {first_window_start}")
    windows = [DateWindow(date_field, None, first_window_start - timedelta(days=1))]
    start = first_window_start
    while start <= through:
        end = _period_end(start, granularity)
        windows.append(DateWindow(date_field, start, end))
        start = end + timedelta(days=1)
    windows.append(DateWindow(date_field, start, None))
    return windows


def windows_partition_axis(windows: list[DateWindow]) -> bool:
    """True when the windows are ordered, adjacent and open at both ends."""
    if not windows or windows[0].start is not None or windows[-1].end is not None:
        return False
    for earlier, later in zip(windows, windows[1:]):
        if earlier.end is None or later.start is None or later.start != earlier.end + timedelta(days=1):
            return False
    return True
