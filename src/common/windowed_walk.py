"""Windowed cursor walks (D-045 option c, activated by D-057).

A scope listed under ``pagination.windowed_scopes`` is not walked with a
single cursor.  Instead one *pass* performs, in this order:

1. a probe of the unwindowed ``total-results`` (``rows=0``);
2. one ordinary :class:`~src.common.walk.CursorWalker` walk per date window,
   each in its own sub-scope ``<scope>__<field>_<from>_<until>`` and each at
   total tolerance 0 (a window that fails is re-walked under a new walk id a
   bounded number of times within the pass);
3. a second probe of the unwindowed total.

The pass is recorded as one *composite* walk manifest of the parent scope,
whose page entries are the window pages renumbered 1..N and whose completion
block carries the window set.  The composite is ``complete`` only when every
window walk is complete and the window totals add up to the probed total,
both before and after the pass.  Everything downstream (flattening, walk
selection, the run manifest) reads the composite like any other walk; the
window manifests and probe responses stay on disk as evidence.

Why this closes the gap a tolerance cannot: a deep cursor walk can skip
records between cursor steps while ``total-results`` stays constant, so the
walker sees a stable total and a smaller item count with no way to tell loss
from concurrent deletion.  Windows keep each cursor walk to a few pages, and
the partition check (sum of window totals == unwindowed total) proves that
the windows together cover the whole set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from .http import Attempt, PoliteClient
from .manifest import (WINDOWED_RULE, PageEntry, WalkManifestWriter, WalkRecord, list_walks, read_walk_manifest,
                       select_walk, utc_now, walk_manifest_path)
from .raw_store import RawStore
from .walk import CursorWalker, PageParser, UrlBuilder, WalkError, close_stale_walks
from .windows import DateWindow, window_scope_id, windows_partition_axis

PROBE_SCOPE_SUFFIX = "__probe"


def probe_scope_id(scope: str) -> str:
    """Sub-scope under which the two unwindowed total probes of a pass are stored."""
    return f"{scope}{PROBE_SCOPE_SUFFIX}"


def _json_validator(body: bytes) -> str | None:
    try:
        json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "response body is not valid JSON"
    return None


class WindowedWalker:
    def __init__(self, *, client: PoliteClient, store: RawStore, manifest_root: Path,
                 run_id: str, source: str, scope: str, windows: list[DateWindow], granularity: str,
                 logger=None, now=utc_now, max_window_attempts: int = 3, max_restarts: int = 3) -> None:
        if not windows_partition_axis(windows):
            raise WalkError(f"window set for {scope} does not partition the date axis")
        if max_window_attempts < 1:
            raise WalkError("max_window_attempts must be at least 1")
        self.client = client
        self.store = store
        self.manifest_root = manifest_root
        self.run_id = run_id
        self.source = source
        self.scope = scope
        self.windows = list(windows)
        self.granularity = granularity
        self.date_field = windows[0].date_field
        self.logger = logger
        self.now = now
        self.max_window_attempts = max_window_attempts
        self.max_restarts = max_restarts

    # ------------------------------------------------------------------ util
    def _log(self, kind: str, **payload) -> None:
        if self.logger is not None:
            self.logger.event(kind, source=self.source, scope=self.scope, **payload)

    def _probe(self, walk_id: str, page: int, url: str, parse_page: PageParser) -> dict:
        """Fetch the unwindowed total; the response is stored under the probe sub-scope."""
        scope = probe_scope_id(self.scope)
        stored: dict = {}

        def on_attempt(attempt: Attempt) -> None:
            request = {**attempt.request_record, "run_id": self.run_id, "walk_id": walk_id,
                       "source": self.source, "scope": scope, "page": page, "cursor_in": "",
                       "headers": self.client.headers, "response_status": attempt.status,
                       "response_headers": attempt.headers, "error": attempt.error,
                       "parameters": parse_qs(urlsplit(attempt.url).query)}
            paths = self.store.write_attempt(self.source, scope, self.run_id, walk_id, page,
                                             attempt.number, request, attempt.body)
            digest = self.store.file_sha256(paths.response_rel)
            attempt.stored_response_rel = paths.response_rel
            attempt.stored_sha256 = digest
            if self.logger is not None:
                self.logger.attempt(scope=scope, walk_id=walk_id, page=page, attempt=attempt.number,
                                    status=attempt.status,
                                    outcome=("accepted" if attempt.accepted
                                             else "retry" if attempt.retryable else "rejected"),
                                    reason=attempt.rejection_reason)
            stored.update(response_path=paths.response_rel, sha256=digest, http_status=attempt.status)

        result = self.client.get_page(url, validator=_json_validator, on_attempt=on_attempt)
        total = None
        if result.accepted is not None:
            try:
                total = parse_page(result.accepted.body).total_results
            except ValueError:
                total = None
        return {"page": page, "url": url, "requested_at_utc": self.now(),
                "total_results": total, **stored}

    def _window_walk(self, window: DateWindow, build_url: UrlBuilder, parse_page: PageParser,
                     initial_cursor: str) -> WalkRecord:
        scope = window_scope_id(self.scope, window)
        walker = CursorWalker(client=self.client, store=self.store, manifest_root=self.manifest_root,
                              run_id=self.run_id, source=self.source, scope=scope, logger=self.logger,
                              now=self.now, max_restarts=self.max_restarts, total_tolerance=0)
        record = None
        for attempt in range(1, self.max_window_attempts + 1):
            record = walker.run(build_url=build_url, parse_page=parse_page, initial_cursor=initial_cursor,
                                force_new_walk=True)
            if record.state == "complete":
                break
            self._log("window_walk_retry" if attempt < self.max_window_attempts else "window_walk_given_up",
                      window=window.label, walk_id=record.walk_id, walk_state=record.state,
                      reason=record.reason, attempt=attempt)
        assert record is not None
        return record

    # ------------------------------------------------------------------ pass
    def run(self, *, build_window_url: Callable[[DateWindow], UrlBuilder], probe_url: str,
            parse_page: PageParser, initial_cursor: str = "", force_new_walk: bool = False) -> WalkRecord:
        """Return the complete composite walk for this scope, performing a pass if needed."""
        close_stale_walks(self.manifest_root, self.run_id, self.source, self.scope, now=self.now)
        existing = list_walks(self.manifest_root, self.run_id, self.source, self.scope)
        if not force_new_walk:
            selected, _ = select_walk(existing, "latest_completed_then_smallest_walk_id")
            if selected:
                self._log("walk_reused", walk_id=selected.walk_id)
                return selected
        walk_id = self.store.new_walk_id(self.source, self.scope, self.run_id, [w.walk_id for w in existing])
        path = walk_manifest_path(self.manifest_root, self.run_id, self.source, self.scope, walk_id)
        writer = WalkManifestWriter(path, self.run_id, self.source, self.scope, walk_id, now=self.now)
        self._log("windowed_walk_start", walk_id=walk_id, date_field=self.date_field,
                  granularity=self.granularity, window_count=len(self.windows))
        results: list[tuple[DateWindow, WalkRecord]] = []
        before = after = None
        completion = {"rule": WINDOWED_RULE, "total_tolerance": 0, "tolerance_reason": "",
                      "date_field": self.date_field, "granularity": self.granularity,
                      "window_count": len(self.windows)}

        def window_records() -> list[dict]:
            return [{**window.as_record(), "scope": window_scope_id(self.scope, window),
                     "walk_id": record.walk_id, "state": record.state,
                     "first_page_total_results": record.completion.get("first_page_total_results"),
                     "accepted_items_total": record.items_total, "pages": len(record.pages),
                     "total_delta": record.completion.get("total_delta"), "reason": record.reason}
                    for window, record in results]

        def finish(state: str, reason: str) -> WalkRecord:
            page_no = 0
            items_total = 0
            for window, record in results:
                for entry in record.pages:
                    page_no += 1
                    items_total += entry.items_in_page
                    writer.accept_page(PageEntry(page=page_no, accepted_attempt=entry.accepted_attempt,
                                                 response_path=entry.response_path, sha256=entry.sha256,
                                                 bytes=entry.bytes, http_status=entry.http_status,
                                                 cursor_in=entry.cursor_in, cursor_out=entry.cursor_out,
                                                 items_in_page=entry.items_in_page,
                                                 accepted_at_utc=entry.accepted_at_utc),
                                       window=window.label, window_walk_id=record.walk_id,
                                       window_page=entry.page)
            totals = [r.completion.get("first_page_total_results") for _, r in results]
            window_sum = sum(totals) if results and all(type(t) is int for t in totals) else None
            t0 = before["total_results"] if before else None
            t1 = after["total_results"] if after else None
            writer.close(state, reason=reason, pages_accepted=page_no, items_total=items_total, completion={
                **completion,
                "windows": window_records(),
                "probe_before": before, "probe_after": after,
                "unwindowed_total_before": t0, "unwindowed_total_after": t1,
                "sum_of_window_totals": window_sum,
                "partition_delta_before": (window_sum - t0) if window_sum is not None and t0 is not None else None,
                "partition_delta_after": (window_sum - t1) if window_sum is not None and t1 is not None else None,
                # Same keys as a single walk so that readers of either form see the whole-set total.
                "first_page_total_results": t0, "last_page_total_results": t1,
                "accepted_items_total": items_total,
                "total_delta": (items_total - t0) if t0 is not None else None,
                "total_results_moved_during_walk": t0 != t1,
                "terminal_evidence": "all_windows_terminal" if state == "complete" else "",
            })
            self._log("walk_failed" if state == "failed" else f"walk_{state}", walk_id=walk_id,
                      reason=reason, pages_accepted=page_no, items_total=items_total,
                      windows_complete=sum(1 for _, r in results if r.is_complete), windows=len(self.windows))
            return read_walk_manifest(path)

        try:
            before = self._probe(walk_id, 1, probe_url, parse_page)
            if before["total_results"] is None:
                return finish("failed", "unwindowed total-results probe failed before the window pass")
            for window in self.windows:
                results.append((window, self._window_walk(window, build_window_url(window), parse_page,
                                                          initial_cursor)))
            after = self._probe(walk_id, 2, probe_url, parse_page)
            if after["total_results"] is None:
                return finish("failed", "unwindowed total-results probe failed after the window pass")
            incomplete = [(w, r) for w, r in results if not r.is_complete]
            if incomplete:
                detail = "; ".join(f"{w.label}: {r.state} ({r.reason})" for w, r in incomplete[:5])
                more = f"; and {len(incomplete) - 5} more" if len(incomplete) > 5 else ""
                return finish("failed", f"{len(incomplete)} of {len(self.windows)} window walk(s) not complete "
                                        f"at tolerance 0 — {detail}{more}")
            window_sum = sum(r.completion["first_page_total_results"] for _, r in results)
            t0, t1 = before["total_results"], after["total_results"]
            if window_sum != t0 or window_sum != t1:
                moved = (f"unwindowed total moved during the pass ({t0} -> {t1})" if t0 != t1
                         else f"unwindowed total stable at {t0}")
                return finish("failed", f"window totals sum to {window_sum} but the unwindowed total-results is "
                                        f"{t0} before and {t1} after the pass; {moved}; records outside every "
                                        f"window (for example without {self.date_field}) or a replica "
                                        f"inconsistency between probes would both show here")
            return finish("complete", f"all {len(self.windows)} window walks complete at tolerance 0 and "
                                      f"window totals sum to the unwindowed total-results {t0} before and after")
        except Exception as exc:
            finish("failed", f"{type(exc).__name__}: {exc}")
            raise
