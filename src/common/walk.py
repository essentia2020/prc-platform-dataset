"""Cursor walks: pages -> immutable raw store -> accepted-page manifest.

A *walk* is one ordered sequence of page requests under one pagination
state.  The rules implemented here:

* every attempt is written to the raw store before the next one is made;
* an accepted page is recorded in the walk manifest with the sha256 of the
  stored bytes;
* when the pagination state becomes unusable (cursor rejected by the
  source), the walk is closed as ``incomplete_restarted`` and a *new* walk
  with a new ``walk_id`` starts from the initial cursor — pages are never
  re-fetched into an existing walk;
* when the attempt budget of a page is exhausted the walk is closed as
  ``failed``;
* only a walk closed as ``complete`` is eligible for downstream use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from .http import Attempt, PoliteClient
from .manifest import (PageEntry, WalkManifestWriter, WalkRecord, list_walks, read_walk_manifest, select_walk,
                       utc_now, walk_manifest_path)
from .raw_store import RawStore, RawStoreError


class WalkError(RuntimeError):
    pass


@dataclass
class ParsedPage:
    items_in_page: int
    next_cursor: str | None     # Continuation only; absence is not a completion rule.
    cursor_invalid: bool = False  # True -> source rejected the pagination state
    total_results: int | None = None
    terminal: bool = False       # Source-specific terminal evidence.


PageParser = Callable[[bytes], ParsedPage]
UrlBuilder = Callable[[str], str]


def _json_validator(body: bytes) -> str | None:
    try:
        json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "response body is not valid JSON"
    return None


def close_stale_walks(manifest_root: Path, run_id: str, source: str, scope: str,
                      now=utc_now) -> list[str]:
    """Mark walks left ``in_progress`` by an interrupted process as restarted.

    Appends one terminal line; never edits or removes existing lines.
    Returns the walk ids that were closed.
    """
    closed = []
    for walk in list_walks(manifest_root, run_id, source, scope):
        if walk.state != "in_progress":
            continue
        path = walk_manifest_path(manifest_root, run_id, source, scope, walk.walk_id)
        line = {"run_id": run_id, "walk_id": walk.walk_id, "source": source, "scope": scope,
                "record": "walk_end", "walk_state": "incomplete_restarted",
                "reason": "walk found in_progress at start of a later invocation; never resumed in place",
                "pages_accepted": len(walk.pages), "items_total": walk.items_total,
                "ended_at_utc": now()}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
        closed.append(walk.walk_id)
    return closed


class CursorWalker:
    def __init__(self, *, client: PoliteClient, store: RawStore, manifest_root: Path,
                 run_id: str, source: str, scope: str, logger=None, now=utc_now,
                 max_restarts: int = 3, total_tolerance: int = 0,
                 tolerance_reason: str = "") -> None:
        if type(total_tolerance) is not int or total_tolerance < 0:
            raise WalkError("total_tolerance must be a nonnegative integer")
        if total_tolerance and not tolerance_reason.strip():
            raise WalkError("a nonzero total tolerance requires a reason")
        self.client = client
        self.store = store
        self.manifest_root = manifest_root
        self.run_id = run_id
        self.source = source
        self.scope = scope
        self.logger = logger
        self.now = now
        self.max_restarts = max_restarts
        self.total_tolerance = total_tolerance
        self.tolerance_reason = tolerance_reason

    # ------------------------------------------------------------------ util
    def _log(self, kind: str, **payload) -> None:
        if self.logger is not None:
            self.logger.event(kind, source=self.source, scope=self.scope, **payload)

    def _persist(self, walk_id: str, page: int, writer: WalkManifestWriter,
                 cursor_in: str) -> Callable[[Attempt], None]:
        def on_attempt(attempt: Attempt) -> None:
            number = self.store.next_attempt_number(self.source, self.scope, self.run_id, walk_id, page)
            if number != attempt.number:
                raise WalkError(f"attempt numbering diverged for page {page}: store expects "
                                f"{number}, client reports {attempt.number}")
            request = {**attempt.request_record, "run_id": self.run_id, "walk_id": walk_id,
                       "source": self.source, "scope": self.scope, "page": page,
                       "cursor_in": cursor_in, "headers": self.client.headers,
                       "response_status": attempt.status,
                       "response_headers": attempt.headers, "error": attempt.error}
            request["parameters"] = parse_qs(urlsplit(attempt.url).query)
            paths = self.store.write_attempt(self.source, self.scope, self.run_id, walk_id, page,
                                             attempt.number, request, attempt.body)
            digest = self.store.file_sha256(paths.response_rel)
            attempt.stored_response_rel = paths.response_rel
            attempt.stored_sha256 = digest
            if not attempt.accepted:
                writer.reject_attempt(page, attempt.number, attempt.status, attempt.rejection_reason,
                                      paths.response_rel, digest)
            if self.logger is not None:
                self.logger.attempt(scope=self.scope, walk_id=walk_id, page=page, attempt=attempt.number,
                                    status=attempt.status,
                                    outcome="accepted" if attempt.accepted else "retry",
                                    reason=attempt.rejection_reason)
        return on_attempt

    # ------------------------------------------------------------------ walk
    def run(self, *, build_url: UrlBuilder, parse_page: PageParser, initial_cursor: str = "",
            force_new_walk: bool = False) -> WalkRecord:
        """Return the complete walk for this scope, performing requests if needed."""
        close_stale_walks(self.manifest_root, self.run_id, self.source, self.scope, now=self.now)
        existing = list_walks(self.manifest_root, self.run_id, self.source, self.scope)
        if not force_new_walk:
            selected, _ = select_walk(existing, "latest_completed_then_smallest_walk_id")
            if selected:
                self._log("walk_reused", walk_id=selected.walk_id)
                return selected
        restarts = 0
        known = [w.walk_id for w in existing]
        while True:
            walk_id = self.store.new_walk_id(self.source, self.scope, self.run_id, known)
            known.append(walk_id)
            record = self._single_walk(walk_id, build_url, parse_page, initial_cursor)
            if record.state == "complete":
                return record
            if record.state == "incomplete_restarted" and restarts < self.max_restarts:
                restarts += 1
                self._log("walk_restart", previous_walk_id=walk_id, restarts=restarts)
                continue
            return record

    def _single_walk(self, walk_id: str, build_url: UrlBuilder, parse_page: PageParser,
                     initial_cursor: str) -> WalkRecord:
        path = walk_manifest_path(self.manifest_root, self.run_id, self.source, self.scope, walk_id)
        writer = WalkManifestWriter(path, self.run_id, self.source, self.scope, walk_id, now=self.now)
        self._log("walk_start", walk_id=walk_id)
        cursor = initial_cursor
        page = 1
        pages_accepted = 0
        items_total = 0
        first_total = None
        seen_urls: set[str] = set()
        completion = {"rule": "crossref_total_checked" if self.source == "crossref" else "sciety_continuation_exhausted",
                      "total_tolerance": self.total_tolerance, "tolerance_reason": self.tolerance_reason}

        def finish(state, reason):
            writer.close(state, reason=reason, pages_accepted=pages_accepted,
                         items_total=items_total, completion={**completion,
                         "first_page_total_results": first_total, "accepted_items_total": items_total})
            return read_walk_manifest(path)

        try:
            while True:
                url = build_url(cursor)
                if self.source == "sciety" and url in seen_urls:
                    return finish("failed", "repeated Sciety continuation URL")
                seen_urls.add(url)
                result = self.client.get_page(url, validator=_json_validator,
                                              on_attempt=self._persist(walk_id, page, writer, cursor))
                accepted = result.accepted
                if accepted is None:
                    last = result.attempts[-1] if result.attempts else None
                    status = last.status if last else None
                    # A definitive 4xx after page 1 means the pagination state was
                    # rejected: close this walk and let the caller start a new one.
                    if page > 1 and status is not None and 400 <= status < 500 and status != 429:
                        writer.close("incomplete_restarted",
                                     reason=f"pagination state rejected with http {status} on page {page}",
                                     pages_accepted=pages_accepted, items_total=items_total)
                        return read_walk_manifest(path)
                    reason = f"attempt budget exhausted on page {page}: {last.rejection_reason if last else 'no attempt'}"
                    writer.close("failed", reason=reason, pages_accepted=pages_accepted,
                                 items_total=items_total)
                    self._log("walk_failed", walk_id=walk_id, page=page, reason=reason)
                    return read_walk_manifest(path)
                parsed = parse_page(accepted.body)
                if parsed.cursor_invalid:
                    writer.close("incomplete_restarted",
                                 reason=f"source reported an unusable cursor on page {page}",
                                 pages_accepted=pages_accepted, items_total=items_total)
                    return read_walk_manifest(path)
                writer.accept_page(PageEntry(
                    page=page, accepted_attempt=accepted.number,
                    response_path=accepted.stored_response_rel,
                    sha256=accepted.stored_sha256, bytes=len(accepted.body),
                    http_status=int(accepted.status or 0), cursor_in=cursor,
                    cursor_out=parsed.next_cursor or "", items_in_page=parsed.items_in_page,
                    accepted_at_utc=self.now()))
                pages_accepted += 1
                items_total += parsed.items_in_page
                if self.source == "crossref":
                    query = parse_qs(urlsplit(url).query)
                    if "sort" in query or "cursor" not in query:
                        return finish("failed", "Crossref requires cursor pagination without sort")
                    rows = int(query.get("rows", ["0"])[0])
                    if rows <= 0:
                        return finish("failed", "Crossref rows must be positive")
                    if page == 1:
                        first_total = parsed.total_results
                    if first_total is None:
                        return finish("failed", "missing or invalid first-page total-results")
                    if not parsed.next_cursor:
                        writer.anomaly("missing_next_cursor", page=page)
                        self._log("missing_next_cursor", walk_id=walk_id, page=page)
                    terminal = parsed.items_in_page < rows
                    completion["terminal_evidence"] = ("empty_page" if parsed.items_in_page == 0
                                                       else "short_page") if terminal else ""
                    if page == 1 and parsed.items_in_page == 0 and first_total != 0:
                        return finish("failed", "empty first page with nonzero total-results")
                    if terminal:
                        delta = items_total - first_total
                        completion["total_delta"] = delta
                        if abs(delta) > self.total_tolerance:
                            return finish("failed", "accepted item total differs from first-page total-results")
                        return finish("complete", "terminal page and item-total check satisfied")
                    if not parsed.next_cursor:
                        return finish("failed", "missing next-cursor without terminal evidence")
                elif parsed.terminal:
                    return finish("complete", "Sciety continuation exhausted after validated article pages")
                elif not parsed.next_cursor:
                    return finish("failed", "missing Sciety continuation without terminal evidence")
                cursor = parsed.next_cursor
                page += 1
        except Exception as exc:
            finish("failed", f"{type(exc).__name__}: {exc}")
            raise
