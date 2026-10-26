"""Structured JSON-lines logging for extraction runs.

Every HTTP attempt and every stage transition is appended as one JSON object
to ``logs/extraction_<run_id>.jsonl``.  The log is operational evidence; the
accepted-page manifest in ``data/manifests/`` remains the authoritative
inventory and resume state.  Lines are never rewritten.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Mapping

from src.common.config import REPO_ROOT

LOG_DIR = REPO_ROOT / "logs"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with second precision."""
    return _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0).isoformat()


class JsonlLogger:
    """Append-only JSON-lines event logger bound to one ``run_id``."""

    def __init__(self, run_id: str, log_dir: Path | str = LOG_DIR) -> None:
        self.run_id = run_id
        self.path = Path(log_dir) / f"extraction_{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, kind: str, **payload: Any) -> Mapping[str, Any]:
        """Append one event; returns the record that was written."""
        record = {"ts_utc": utc_now_iso(), "run_id": self.run_id, "event": kind}
        record.update(payload)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def attempt(
        self,
        *,
        scope: str,
        walk_id: str,
        page: int,
        attempt: int,
        status: int | None,
        outcome: str,
        **extra: Any,
    ) -> Mapping[str, Any]:
        """Log one HTTP attempt (``outcome``: accepted / retry / rejected / failed / restart).

        ``rejected`` marks a definitive answer from the source (HTTP 4xx other
        than 429) that is not retried.
        """
        return self.event(
            "http_attempt",
            scope=scope,
            walk_id=walk_id,
            page=page,
            attempt=attempt,
            http_status=status,
            outcome=outcome,
            **extra,
        )
