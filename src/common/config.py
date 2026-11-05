"""Configuration loader for ``config/run.yaml`` and ``config/sources.yaml``.

``config/run.yaml`` is the single declaration point for ``run_id``,
``analysis_cutoff_date``, ``mailto`` and ``selected_walk_policy``.  Loading
fails loudly when any required field is missing or malformed; defaults are
never substituted, because the run configuration states the intention of a
run and must be explicit.  Facts about an actual retrieval live in the
run-level manifest (``data/manifests/<run_id>.json``), never in this file.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
RUN_CONFIG_PATH = CONFIG_DIR / "run.yaml"
SOURCES_CONFIG_PATH = CONFIG_DIR / "sources.yaml"

REQUIRED_RUN_FIELDS = (
    "run_id",
    "analysis_cutoff_date",
    "mailto",
    "selected_walk_policy",
)
ALLOWED_WALK_POLICIES = ("latest_completed_then_smallest_walk_id",)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{2,63}$")
_MAILTO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ConfigError(ValueError):
    """Raised when a configuration file is missing, incomplete or invalid."""


@dataclass(frozen=True)
class RunConfig:
    """Validated content of ``config/run.yaml``."""

    run_id: str
    analysis_cutoff_date: _dt.date
    mailto: str
    selected_walk_policy: str
    user_agent_label: str = "prc-platform-dataset"
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def cutoff_is_year_end(self) -> bool:
        """True when the cutoff falls on 31 December (no partial year)."""
        return self.analysis_cutoff_date.month == 12 and self.analysis_cutoff_date.day == 31

    @property
    def cutoff_year(self) -> int:
        return self.analysis_cutoff_date.year

    def user_agent(self) -> str:
        """Value of the HTTP User-Agent header for polite-pool requests."""
        return f"{self.user_agent_label}/1.4.0 (mailto:{self.mailto})"


def _read_yaml(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, Mapping):
        raise ConfigError(f"configuration file is not a mapping: {path}")
    return data


def _parse_date(value: Any, field_name: str) -> _dt.date:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        try:
            return _dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ConfigError(f"{field_name} must be an ISO date (YYYY-MM-DD): {value!r}") from exc
    raise ConfigError(f"{field_name} must be an ISO date (YYYY-MM-DD): {value!r}")


def load_run_config(path: Path | str = RUN_CONFIG_PATH) -> RunConfig:
    """Load and validate ``config/run.yaml``.

    Raises ``ConfigError`` if any of ``REQUIRED_RUN_FIELDS`` is missing or
    empty, if ``run_id`` is not a safe path component, if ``mailto`` is not an
    e-mail address, or if ``selected_walk_policy`` is not a known policy.
    """
    path = Path(path)
    data = _read_yaml(path)
    missing = [name for name in REQUIRED_RUN_FIELDS if data.get(name) in (None, "")]
    if missing:
        raise ConfigError(f"{path}: missing required field(s): {', '.join(missing)}")

    run_id = str(data["run_id"])
    if not _RUN_ID_RE.match(run_id):
        raise ConfigError(f"{path}: run_id must match {_RUN_ID_RE.pattern}: {run_id!r}")
    # PRC_MAILTO overrides the configured address without editing the tracked
    # file (internal pre-submission review, 2026-11-05, item S10).
    mailto = os.environ.get("PRC_MAILTO") or str(data["mailto"])
    if not _MAILTO_RE.match(mailto):
        raise ConfigError(f"{path}: mailto must be an e-mail address: {mailto!r}")
    policy = str(data["selected_walk_policy"])
    if policy not in ALLOWED_WALK_POLICIES:
        raise ConfigError(
            f"{path}: selected_walk_policy must be one of {ALLOWED_WALK_POLICIES}: {policy!r}"
        )
    cutoff = _parse_date(data["analysis_cutoff_date"], "analysis_cutoff_date")

    extra = {k: v for k, v in data.items() if k not in REQUIRED_RUN_FIELDS}
    label = str(extra.pop("user_agent_label", "prc-platform-dataset"))
    return RunConfig(
        run_id=run_id,
        analysis_cutoff_date=cutoff,
        mailto=mailto,
        selected_walk_policy=policy,
        user_agent_label=label,
        extra=extra,
    )


def load_sources_config(path: Path | str = SOURCES_CONFIG_PATH) -> Mapping[str, Any]:
    """Load ``config/sources.yaml`` and check that both sources are declared."""
    data = _read_yaml(Path(path))
    sources = data.get("sources")
    if not isinstance(sources, Mapping):
        raise ConfigError(f"{path}: top-level key 'sources' must be a mapping")
    for required in ("crossref", "sciety"):
        if required not in sources:
            raise ConfigError(f"{path}: source {required!r} is not declared")
        for key in ("base_url", "licence", "rate_limit"):
            if key not in sources[required]:
                raise ConfigError(f"{path}: source {required!r} lacks field {key!r}")
    return data
