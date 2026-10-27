"""Interim CSV layer (``data/interim/``, outside Git).

Column lists follow docs/data_dictionary.md §4.  Files are written whole,
from a *complete* walk only; a failed or incomplete walk writes nothing.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_INTERIM_ROOT = Path("data") / "interim"
INTERIM_ROOT_ENV = "PRC_INTERIM_ROOT"

CROSSREF_WORK_COLUMNS = [
    "doi", "doi_original", "type", "title", "prefix", "member", "container_title",
    "created", "deposited", "indexed", "issued", "posted", "published_online", "published_print",
    "relation_is_review_of", "relation_json", "retrieved_at_utc", "platform_id", "walk_id", "page", "accepted_attempt",
    "attribution_basis", "included", "exclusion_reason",
]
CROSSREF_REVIEW_COLUMNS = CROSSREF_WORK_COLUMNS + ["target_id_raw", "target_id_type", "target_flag",
                                                  "target_relation_type"]
SCIETY_EVALUATION_COLUMNS = [
    "group_id", "group_name", "docmap_id", "evaluation_index", "evaluated_work_doi", "evaluation_id",
    "evaluation_url", "evaluation_doi", "evaluation_date", "evaluation_type", "retrieved_at_utc",
    "platform_id", "walk_id", "page", "accepted_attempt",
]


def resolve_interim_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get(INTERIM_ROOT_ENV)
    return Path(env) if env else DEFAULT_INTERIM_ROOT


def write_csv(path: Path, columns: list[str], rows: Iterable[Mapping[str, object]]) -> int:
    """Write ``rows`` atomically; returns the number of data rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})
            count += 1
    os.replace(tmp, path)
    return count


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
