"""Per-row technical state derived from the run-level manifest (§9.4, §9.7).

The run manifest (``data/manifests/<run_id>/<run_id>.json``) records, for
every retrieval scope, the walks of the run and the selected complete walk.
This module maps that scope-level state onto register rows:

* a row is ``complete`` only when every *primary* scope it depends on has a
  selected complete walk;
* a row is ``failed`` when at least one primary scope is failed and none is
  still incomplete;
* otherwise the row is ``incomplete`` (including scopes never attempted).

Scopes declared with ``role: cross_check`` in the row's selector are not
counting sources.  Their state is reported separately and never blocks a
row's analytical outputs; when a cross-check scope is not complete, the
cross-source evaluation identity simply cannot be confirmed for that row.

Nothing here reads interim or raw files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..extract.selectors import (REVIEW_RECORD_TYPE, compile_crossref_selector, crossref_scopes,
                                 sciety_scopes)
from .manifest import load_run_manifest, run_manifest_path

EXTRACTION_STATUSES = ("complete", "incomplete", "failed")


@dataclass
class RowState:
    row_id: str
    register_status: str
    primary_scopes: dict[str, str] = field(default_factory=dict)      # "<source>/<scope>" -> status
    cross_check_scopes: dict[str, str] = field(default_factory=dict)
    selected_walks: dict[str, str | None] = field(default_factory=dict)

    @property
    def extraction_status(self) -> str:
        """``complete`` / ``incomplete`` / ``failed`` over the primary scopes."""
        if not self.primary_scopes:
            return "incomplete"
        states = set(self.primary_scopes.values())
        if states == {"complete"}:
            return "complete"
        if "incomplete" in states or "not_run" in states:
            return "incomplete"
        return "failed"

    @property
    def blocking_scopes(self) -> list[str]:
        return sorted(k for k, v in self.primary_scopes.items() if v != "complete")

    @property
    def cross_check_complete(self) -> bool:
        return bool(self.cross_check_scopes) and set(self.cross_check_scopes.values()) == {"complete"}


def _scope_status(manifest: Mapping[str, Any], key: str) -> tuple[str, str | None]:
    entry = (manifest.get("scopes") or {}).get(key)
    if not entry:
        return "not_run", None
    status = str(entry.get("extraction_status") or "incomplete")
    if status not in EXTRACTION_STATUSES:
        status = "incomplete"
    return status, entry.get("selected_walk_id")


def row_scopes(row: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """``(primary_scope_keys, cross_check_scope_keys)`` for one register row."""
    primary: list[str] = []
    cross: list[str] = []
    selector = row.get("extraction_selector") or {}
    crossref_block = selector.get("crossref") if isinstance(selector, Mapping) else None
    if isinstance(crossref_block, Mapping) and row.get("data_source") in ("crossref", "both"):
        sel = compile_crossref_selector(row)
        if sel is not None and not sel.pending:
            keys = [f"crossref/{s.scope_id}" for s in crossref_scopes([sel])]
            (cross if crossref_block.get("role") == "cross_check" else primary).extend(keys)
    sciety_block = selector.get("sciety") if isinstance(selector, Mapping) else None
    if isinstance(sciety_block, Mapping) and row.get("data_source") in ("sciety", "both"):
        keys = [f"sciety/{s.scope_id}" for s in sciety_scopes([row])]
        (cross if sciety_block.get("role") == "cross_check" else primary).extend(keys)
    return primary, cross


def row_states(manifest: Mapping[str, Any], platforms: list[Mapping[str, Any]]) -> dict[str, RowState]:
    states: dict[str, RowState] = {}
    for row in platforms:
        state = RowState(row_id=str(row["row_id"]), register_status=str(row.get("register_status") or ""))
        primary, cross = row_scopes(row)
        for key in primary:
            state.primary_scopes[key], state.selected_walks[key] = _scope_status(manifest, key)
        for key in cross:
            state.cross_check_scopes[key], state.selected_walks[key] = _scope_status(manifest, key)
        states[state.row_id] = state
    return states


def load_row_states(manifest_root: Path, run_id: str, platforms: list[Mapping[str, Any]]
                    ) -> tuple[dict, dict[str, RowState]]:
    manifest = load_run_manifest(run_manifest_path(Path(manifest_root), run_id))
    return manifest, row_states(manifest, platforms)


def review_scope_keys(row: Mapping[str, Any]) -> list[str]:
    """Primary Crossref peer-review scope keys of a row (used for review-stage dependencies)."""
    sel = compile_crossref_selector(row)
    if sel is None or sel.pending:
        return []
    return [f"crossref/{s.scope_id}" for s in crossref_scopes([sel], "reviews")
            if s.record_type == REVIEW_RECORD_TYPE]
