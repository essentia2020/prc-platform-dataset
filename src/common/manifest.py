"""Accepted-page manifests and the run-level manifest.

Walk manifest: ``data/manifests/<run_id>/<source>__<scope>__<walk_id>.manifest.jsonl``
(one JSON object per line, append-only; schema in docs/data_dictionary.md §3.2).

Run manifest: ``data/manifests/<run_id>/<run_id>.json`` (schema §3.3).

Only *complete* walks are ever selected for downstream use.  A walk whose
terminal state is ``incomplete_restarted`` or ``failed`` — or which has no
terminal line at all — contributes nothing to any count.
"""

from __future__ import annotations

import gzip
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

WALK_STATES = ("in_progress", "complete", "incomplete_restarted", "failed")
TERMINAL_STATES = ("complete", "incomplete_restarted", "failed")
SELECTED_WALK_POLICIES = ("latest_completed_then_smallest_walk_id",)
DEFAULT_MANIFEST_ROOT = Path("data") / "manifests"
# Completion rule of a composite walk assembled from date-window walks (D-057).
WINDOWED_RULE = "crossref_windowed_total_checked"


class ManifestError(RuntimeError):
    """Raised on malformed or inconsistent manifests."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def walk_manifest_path(manifest_root: Path, run_id: str, source: str, scope: str,
                       walk_id: str) -> Path:
    return manifest_root / run_id / f"{source}__{scope}__{walk_id}.manifest.jsonl"


def run_manifest_path(manifest_root: Path, run_id: str) -> Path:
    return manifest_root / run_id / f"{run_id}.json"


# --------------------------------------------------------------------- walks
@dataclass
class PageEntry:
    page: int
    accepted_attempt: int
    response_path: str
    sha256: str
    bytes: int
    http_status: int
    cursor_in: str
    cursor_out: str
    items_in_page: int
    accepted_at_utc: str


@dataclass
class WalkRecord:
    run_id: str
    walk_id: str
    source: str
    scope: str
    pages: list[PageEntry] = field(default_factory=list)
    state: str = "in_progress"
    started_at_utc: str = ""
    ended_at_utc: str = ""
    reason: str = ""
    completion: dict = field(default_factory=dict)
    anomalies: list[dict] = field(default_factory=list)

    @property
    def items_total(self) -> int:
        return sum(p.items_in_page for p in self.pages)

    @property
    def is_complete(self) -> bool:
        return self.state == "complete"


class WalkManifestWriter:
    """Append-only writer; one instance per walk."""

    def __init__(self, path: Path, run_id: str, source: str, scope: str, walk_id: str,
                 now=utc_now) -> None:
        self.path = path
        self.identity = {"run_id": run_id, "walk_id": walk_id, "source": source, "scope": scope}
        self._now = now
        self._closed = False
        if path.exists() and path.stat().st_size > 0:
            raise ManifestError(f"walk manifest already exists: {path}; walks are never resumed "
                                "in place — allocate a new walk_id")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._append({"record": "walk_header", "started_at_utc": self._now(),
                      "walk_state": "in_progress"})

    def _append(self, payload: dict) -> None:
        if self._closed:
            raise ManifestError("walk manifest is closed")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({**self.identity, **payload}, ensure_ascii=False,
                                    sort_keys=True) + "\n")

    def accept_page(self, entry: PageEntry, **extra) -> None:
        """Record an accepted page; ``extra`` carries provenance such as the window of a composite walk."""
        self._append({"record": "page", "walk_state": "in_progress", **entry.__dict__, **extra})

    def reject_attempt(self, page: int, attempt: int, http_status: int | None,
                       reason: str, response_path: str | None, sha256: str | None) -> None:
        self._append({"record": "rejected_attempt", "walk_state": "in_progress", "page": page,
                      "attempt": attempt, "http_status": http_status, "reason": reason,
                      "response_path": response_path, "sha256": sha256})

    def anomaly(self, code: str, **details) -> None:
        self._append({"record": "anomaly", "code": code, **details})

    def close(self, state: str, reason: str = "", pages_accepted: int = 0,
              items_total: int = 0, completion: dict | None = None) -> None:
        if state not in TERMINAL_STATES:
            raise ManifestError(f"not a terminal walk state: {state}")
        self._append({"record": "walk_end", "walk_state": state, "reason": reason,
                      "pages_accepted": pages_accepted, "items_total": items_total,
                      "ended_at_utc": self._now(), "completion": completion or {}})
        self._closed = True


def read_walk_manifest(path: Path) -> WalkRecord:
    """Parse a walk manifest.  Missing terminal line -> state ``in_progress``."""
    record: WalkRecord | None = None
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{path}:{line_no}: invalid JSON") from exc
        if record is None:
            try:
                record = WalkRecord(obj["run_id"], obj["walk_id"], obj["source"], obj["scope"])
            except KeyError as exc:
                raise ManifestError(f"{path}:{line_no}: missing identity field {exc}") from exc
        kind = obj.get("record")
        if kind == "walk_header":
            record.started_at_utc = obj.get("started_at_utc", "")
        elif kind == "page":
            record.pages.append(PageEntry(
                page=int(obj["page"]), accepted_attempt=int(obj["accepted_attempt"]),
                response_path=obj["response_path"], sha256=obj["sha256"],
                bytes=int(obj["bytes"]), http_status=int(obj["http_status"]),
                cursor_in=obj.get("cursor_in", ""), cursor_out=obj.get("cursor_out", ""),
                items_in_page=int(obj["items_in_page"]),
                accepted_at_utc=obj.get("accepted_at_utc", "")))
        elif kind == "walk_end":
            state = obj.get("walk_state")
            if state not in TERMINAL_STATES:
                raise ManifestError(f"{path}:{line_no}: invalid terminal state {state!r}")
            record.state = state
            record.ended_at_utc = obj.get("ended_at_utc", "")
            record.reason = obj.get("reason", "")
            record.completion = obj.get("completion", {})
        elif kind == "anomaly":
            record.anomalies.append(obj)
        elif kind == "rejected_attempt":
            continue
        else:
            raise ManifestError(f"{path}:{line_no}: unknown record kind {kind!r}")
    if record is None:
        raise ManifestError(f"{path}: empty manifest")
    pages = [p.page for p in record.pages]
    if record.state == "complete" and pages != list(range(1, len(pages) + 1)):
        raise ManifestError(f"{path}: complete walk with non-contiguous pages {pages}")
    return record


def list_walks(manifest_root: Path, run_id: str, source: str, scope: str) -> list[WalkRecord]:
    folder = manifest_root / run_id
    if not folder.is_dir():
        return []
    prefix = f"{source}__{scope}__"
    walks = [read_walk_manifest(p) for p in sorted(folder.glob(f"{prefix}w*.manifest.jsonl"))]
    # The glob alone would also admit a sub-scope whose own name starts with
    # ``w``; the identity line of each manifest is authoritative.
    walks = [w for w in walks if w.source == source and w.scope == scope]
    return sorted(walks, key=lambda w: w.walk_id)


# ----------------------------------------------------------------- selection
def select_walk(walks: list[WalkRecord], policy: str) -> tuple[WalkRecord | None, str]:
    """Return ``(selected_walk, reason)``; ``None`` when no complete walk exists."""
    if policy not in SELECTED_WALK_POLICIES:
        raise ManifestError(f"unknown selected_walk_policy {policy!r}")
    complete = [w for w in walks if w.is_complete]
    if not complete:
        states = ", ".join(f"{w.walk_id}={w.state}" for w in walks) or "no walks"
        return None, f"no complete walk ({states})"
    latest = max(w.ended_at_utc for w in complete)
    candidates = sorted((w for w in complete if w.ended_at_utc == latest), key=lambda w: w.walk_id)
    chosen = candidates[0]
    reason = f"complete walk with latest ended_at_utc {latest}"
    if len(candidates) > 1:
        reason += f"; tie among {[w.walk_id for w in candidates]} resolved by smallest walk_id"
    return chosen, reason


# ------------------------------------------------------------- run manifest
def load_run_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_run_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def software_record(repo_root: Path | None = None) -> dict:
    """Interpreter, platform and repository commit for the run manifest.

    The commit is read from ``git rev-parse HEAD`` when a repository is
    available; otherwise the field says so instead of being left blank.
    """
    record = {"python": platform.python_version(), "implementation": platform.python_implementation(),
              "platform": platform.platform(), "executable": sys.executable}
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=10, check=False)
        commit = proc.stdout.strip() if proc.returncode == 0 else ""
        dirty = ""
        if commit:
            status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                                    capture_output=True, text=True, timeout=10, check=False)
            dirty = "dirty" if status.returncode == 0 and status.stdout.strip() else "clean"
    except (OSError, subprocess.SubprocessError):
        commit, dirty = "", ""
    record["git_commit"] = commit or "unavailable"
    record["git_worktree"] = dirty or "unavailable"
    return record


_SOFTWARE_CACHE: dict = {}


def _software_once() -> dict:
    """``software_record()`` evaluated once per process (one invocation = one code state)."""
    if "record" not in _SOFTWARE_CACHE:
        _SOFTWARE_CACHE["record"] = software_record()
    return dict(_SOFTWARE_CACHE["record"])


def update_run_manifest_scope(path: Path, *, run_id: str, cutoff: str, policy: str,
                              source: str, scope: str, walks: list[WalkRecord],
                              software: dict | None = None, now=utc_now, extra: dict | None = None) -> dict:
    """Record all walks of one scope and the selected walk under the policy.

    ``extra`` is merged into the scope entry (for example the ``window_set``
    of a windowed scope).  Each entry also records the software in effect
    when it was written, because a run may be extended by later invocations
    under newer code than the run-level ``software`` record.
    """
    payload = load_run_manifest(path) or {
        "run_id": run_id, "analysis_cutoff_date": cutoff, "selected_walk_policy": policy,
        "retrieval_started_at": now(), "retrieval_finished_at": "", "scopes": {},
        "software": software if software is not None else software_record()}
    if payload.get("run_id") != run_id:
        raise ManifestError(f"run manifest {path} belongs to run {payload.get('run_id')!r}")
    selected, reason = select_walk(walks, policy)
    if selected is not None:
        status = "complete"
    elif any(w.state == "failed" for w in walks) and not any(w.state == "in_progress" for w in walks):
        status = "failed"
    else:
        status = "incomplete"
    payload["scopes"][f"{source}/{scope}"] = {
        "source": source, "scope": scope,
        "walk_ids": [w.walk_id for w in walks],
        "walk_states": {w.walk_id: w.state for w in walks},
        "selected_walk_id": selected.walk_id if selected else None,
        "selection_reason": reason,
        "extraction_status": status,
        "completed_at": selected.ended_at_utc if selected else None,
        "pages": len(selected.pages) if selected else None,
        "items": selected.items_total if selected else None,
        "completion": selected.completion if selected else None,
        "anomalies": selected.anomalies if selected else [],
        "recorded_at": now(),
        "software": software if software is not None else _software_once(),
        **(extra or {}),
    }
    payload["retrieval_finished_at"] = now()
    write_run_manifest(path, payload)
    return payload


def verify_walk_against_store(walk: WalkRecord, raw_root: Path) -> list[str]:
    """Return a list of mismatches between manifest digests and stored bytes."""
    from .raw_store import sha256_of_file  # local import keeps modules decoupled

    problems = []
    for page in walk.pages:
        target = raw_root / page.response_path
        if not target.is_file():
            problems.append(f"{walk.walk_id} page {page.page}: missing {page.response_path}")
            continue
        actual = sha256_of_file(target)
        if actual != page.sha256:
            problems.append(f"{walk.walk_id} page {page.page}: sha256 mismatch")
    return problems


# --- walk shape -------------------------------------------------------------
#
# ``total_delta == 0`` shows that the accepted item total equals the first-page
# total-results; it is a necessary condition, not a proof that the cursor was
# never reset.  A reset re-serves pages, so the direct observables are the page
# sequence itself: a cursor value seen twice, more non-empty pages than the
# total allows, a short page before the terminal one, or the same record on
# two pages.  ``walk_shape_issues`` reports these from the walk manifest (and
# from the raw store when it is available); it never changes a walk state.

def _read_response_payload(path: Path) -> dict:
    """Parse a stored response, gzip-compressed (``.gz``, as the raw store writes it) or plain."""
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            raw = handle.read()
    else:
        raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def expected_pages(first_total: int | None, rows: int) -> int | None:
    """Number of non-empty pages a stable result set yields at ``rows`` per page."""
    if first_total is None or rows <= 0:
        return None
    return -(-first_total // rows)


def walk_shape_issues(walk: WalkRecord, rows: int, raw_root: Path | None = None) -> list[str]:
    """Return shape problems of a complete Crossref cursor walk (empty list = consistent).

    Checks, in order: repeated ``cursor_in`` (a reset or a loop), the number
    of non-empty pages against ``ceil(first_page_total_results / rows)``, at
    most one trailing empty page, no short page before the last non-empty
    page, and — when ``raw_root`` is given — no DOI accepted on two pages.
    Pages absent from the raw store make the last check inconclusive, which
    is reported as an issue rather than passed over.  Walks of other states
    are not judged (they contribute nothing anyway).

    A composite walk (completion rule ``crossref_windowed_total_checked``)
    is judged by its own rules instead of 1-4: every window walk complete,
    window totals equal to the unwindowed total before and after the pass,
    and — with ``raw_root`` — no DOI accepted on two pages across windows.
    The window walks themselves are ordinary walks and are judged by 1-5
    under their own sub-scope.
    """
    if walk.state != "complete":
        return []
    if walk.completion.get("rule") == WINDOWED_RULE:
        return _composite_shape_issues(walk, raw_root)
    issues: list[str] = []
    cursors = [p.cursor_in for p in walk.pages]
    repeated = sorted({c for c in cursors if c and cursors.count(c) > 1})
    if repeated:
        issues.append(f"cursor_in repeated on {len(repeated)} value(s): the walk re-served pages")
    non_empty = [p for p in walk.pages if p.items_in_page > 0]
    empty = [p for p in walk.pages if p.items_in_page == 0]
    first_total = walk.completion.get("first_page_total_results")
    want = expected_pages(first_total, rows)
    if want is not None and len(non_empty) != want:
        issues.append(f"{len(non_empty)} non-empty page(s) for total-results {first_total} at rows={rows} "
                      f"(expected {want})")
    if len(empty) > 1 or (empty and empty[-1].page != walk.pages[-1].page):
        issues.append("empty page before the terminal page")
    for p in non_empty[:-1]:
        if p.items_in_page < rows:
            issues.append(f"short page {p.page} ({p.items_in_page} < {rows}) before the last non-empty page")
    if raw_root is not None:
        issues.extend(_duplicate_record_issues(walk.pages, raw_root))
    return issues


def _composite_shape_issues(walk: WalkRecord, raw_root: Path | None) -> list[str]:
    issues: list[str] = []
    completion = walk.completion
    windows = completion.get("windows") or []
    if not windows:
        issues.append("composite walk without a window list")
    declared = completion.get("window_count")
    if declared is not None and declared != len(windows):
        issues.append(f"window_count {declared} differs from {len(windows)} listed window(s)")
    not_complete = [w for w in windows if w.get("state") != "complete"]
    if not_complete:
        issues.append(f"{len(not_complete)} window walk(s) not complete: "
                      + ", ".join(str(w.get("label")) for w in not_complete[:5]))
    totals = [w.get("first_page_total_results") for w in windows]
    if any(type(t) is not int for t in totals):
        issues.append("a window is missing first_page_total_results")
    else:
        window_sum = sum(totals)
        for key in ("unwindowed_total_before", "unwindowed_total_after"):
            total = completion.get(key)
            if type(total) is not int:
                issues.append(f"{key} missing")
            elif total != window_sum:
                issues.append(f"window totals sum to {window_sum} but {key} is {total}")
    if sum(int(w.get("pages") or 0) for w in windows) != len(walk.pages):
        issues.append(f"{len(walk.pages)} composite page(s) but the windows account for "
                      f"{sum(int(w.get('pages') or 0) for w in windows)}")
    if raw_root is not None:
        issues.extend(_duplicate_record_issues(walk.pages, raw_root))
    return issues


def _duplicate_record_issues(pages: list[PageEntry], raw_root: Path) -> list[str]:
    """Rule 5: no DOI accepted on two pages; missing raw pages make it inconclusive."""
    issues: list[str] = []
    seen: dict[str, int] = {}
    duplicates = 0
    missing = 0
    unreadable = 0
    for p in pages:
        target = raw_root / p.response_path
        if not target.is_file():
            missing += 1
            continue
        try:
            payload = _read_response_payload(target)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            unreadable += 1
            continue
        for item in (payload.get("message") or {}).get("items") or []:
            doi = str(item.get("DOI", "")).strip().lower()
            if not doi:
                continue
            if doi in seen and seen[doi] != p.page:
                duplicates += 1
            seen.setdefault(doi, p.page)
    if duplicates:
        issues.append(f"{duplicates} record(s) accepted on more than one page")
    if missing or unreadable:
        issues.append(f"raw store: {missing} page(s) missing, {unreadable} unreadable; "
                      "the duplicate-record check is inconclusive")
    return issues
