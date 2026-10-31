"""Offline transport and run context for extraction tests.

No test in this directory opens a network connection.  The transport below
answers Crossref and Sciety URLs from ``tests/fixtures/`` and returns an empty
page for every scope without a fixture.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from src.common.config import RunConfig, load_sources_config
from src.common.interim import read_csv
from src.common.log import JsonlLogger
from src.common.register import load_platforms

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]
CROSSREF = FIXTURES / "crossref"
SCIETY = FIXTURES / "sciety"

EMPTY_CROSSREF = json.dumps({"status": "ok", "message-type": "work-list",
                             "message": {"items": [], "next-cursor": None, "total-results": 0}}).encode()
EMPTY_SCIETY = json.dumps({"articles": []}).encode()


def make_run_config(cutoff: str = "2026-09-30", run_id: str = "run_test_01") -> RunConfig:
    return RunConfig(run_id=run_id, analysis_cutoff_date=date.fromisoformat(cutoff),
                     mailto="offline@example.invalid", selected_walk_policy="latest_completed_then_smallest_walk_id",
                     user_agent_label="prc-platform-dataset-tests", extra={})


_DATE_FILTER_FIELDS = {"issued": "issued", "created": "created", "deposit": "deposited", "posted": "posted",
                       "pub": "published", "index": "indexed"}


def _item_date(item: dict, field: str) -> str | None:
    """ISO day of a Crossref date field; partial dates take the first day/month."""
    value = item.get(field) or {}
    parts = (value.get("date-parts") or [[]])[0] if isinstance(value, dict) else []
    if parts and parts[0]:
        y, m, d = (list(parts) + [1, 1])[:3]
        return f"{int(y):04d}-{int(m or 1):02d}-{int(d or 1):02d}"
    stamp = value.get("date-time") if isinstance(value, dict) else None
    return str(stamp)[:10] if stamp else None


def _within_date_filters(item: dict, filters: dict[str, str]) -> bool:
    """Apply from-/until-<field>-date filters (inclusive) the way the live API does."""
    for name, bound in filters.items():
        if not (name.startswith("from-") or name.startswith("until-")) or not name.endswith("-date"):
            continue
        stem = name.split("-", 1)[1][: -len("-date")]
        field = _DATE_FILTER_FIELDS.get(stem)
        if field is None:
            continue
        day = _item_date(item, field)
        if day is None:
            return False
        if name.startswith("from-") and day < bound:
            return False
        if name.startswith("until-") and day > bound:
            return False
    return True


class FixtureTransport:
    """Callable ``(url, headers, timeout) -> (status, headers, body)``.

    ``scripted`` maps a URL substring to a list of responses consumed in
    order; it lets tests inject 429s, 5xx, cursor errors or transport errors.
    """

    def __init__(self, scripted: dict[str, list] | None = None) -> None:
        self.scripted = {k: list(v) for k, v in (scripted or {}).items()}
        self.requests: list[dict] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float):
        self.requests.append({"url": url, "headers": dict(headers)})
        for needle, queue in self.scripted.items():
            if needle in url and queue:
                response = queue.pop(0)
                if isinstance(response, Exception):
                    raise response
                return response
        parts = urlsplit(url)
        if parts.netloc == "api.crossref.org":
            return 200, {}, self._crossref(parse_qs(parts.query))
        if parts.netloc == "sciety.org":
            return 200, {}, self._sciety(parse_qs(parts.query))
        return 404, {}, b"{}"

    @staticmethod
    def _crossref(query: dict[str, list[str]]) -> bytes:
        filters = dict(item.split(":", 1) for item in query.get("filter", [""])[0].split(",") if ":" in item)
        prefix, record_type = filters.get("prefix", ""), filters.get("type", "")
        if not prefix and filters.get("issn"):
            prefix = f"issn_{filters['issn']}"  # fixture files follow the scope id
        cursor = unquote(query.get("cursor", ["*"])[0])
        page = 1
        match = re.match(r"CURSOR-\w+-(\d+)$", cursor)
        if match:
            page = int(match.group(1))
        paths = sorted(CROSSREF.glob(f"works__{prefix}__{record_type}__page*.json"))
        if not paths:
            return EMPTY_CROSSREF
        items = [item for path in paths for item in json.loads(path.read_bytes())["message"]["items"]]
        items = [item for item in items if _within_date_filters(item, filters)]
        rows = int(query.get("rows", ["1000"])[0])
        part = items[(page - 1) * rows:page * rows]
        tag = "QPC" if (prefix, record_type) == ("10.32388", "posted-content") else "DATA"
        return json.dumps({"status": "ok", "message": {"items": part,
                          "total-results": len(items),
                          "next-cursor": f"CURSOR-{tag}-{page + 1}" if part else None}}).encode()

    @staticmethod
    def _sciety(query: dict[str, list[str]]) -> bytes:
        account = unquote(query.get("publisheraccount", [""])[0])
        if not account:
            # Unfiltered index (coverage probe, D-058): every group fixture in one response,
            # foreign docmaps included, as the live index serves them.
            articles = []
            for fixture in sorted(SCIETY.glob("index__*.json")):
                articles.extend(json.loads(fixture.read_bytes())["articles"])
            return json.dumps({"articles": articles}).encode()
        slug = account.rstrip("/").rsplit("/", 1)[-1]
        path = SCIETY / f"index__{slug}.json"
        if not path.exists():
            return EMPTY_SCIETY
        payload = json.loads(path.read_bytes())
        # The default response models a correctly filtered endpoint. The full
        # fixture is injected separately to test publisher-mismatch failure.
        payload["articles"] = [d for d in payload["articles"]
                               if d["publisher"]["name"] != "Other group"]
        return json.dumps(payload).encode()


def crossref_page(status: int, payload: dict | None = None, headers: dict | None = None, body: bytes | None = None):
    data = body if body is not None else json.dumps(payload or {}).encode()
    return status, dict(headers or {}), data


def run_context(tmp_path: Path, cutoff: str = "2026-09-30"):
    """``(run_config, sources_config, platforms, logger, roots)`` for one test."""
    run_config = make_run_config(cutoff)
    roots = {"raw_root": tmp_path / "raw", "manifest_root": tmp_path / "manifests",
             "interim_root": tmp_path / "interim"}
    logger = JsonlLogger(run_config.run_id, log_dir=tmp_path / "logs")
    sources = load_sources_config()
    sources["sources"]["crossref"]["pagination"]["rows"] = 3
    return run_config, sources, load_platforms(), logger, roots


# ------------------------------------------------------- full offline runs
@dataclass
class PipelineOutputs:
    root: Path
    run_config: RunConfig
    platforms: list
    roots: dict
    processed: Path
    tables: Path
    figures: Path
    checksums: Path
    extraction_error: Exception | None
    analysis_manifest: dict

    def table(self, name: str) -> list[dict]:
        return read_csv(self.tables / f"{name}.csv")

    def cells(self, name: str, **where) -> list[dict]:
        return [r for r in self.table(name) if all(str(r.get(k)) == str(v) for k, v in where.items())]

    def cell(self, name: str, **where) -> dict:
        rows = self.cells(name, **where)
        assert len(rows) == 1, (name, where, len(rows))
        return rows[0]

    def works(self, row_id: str | None = None) -> list[dict]:
        rows = read_csv(self.processed / "works_included.csv")
        return [r for r in rows if row_id is None or r["row_id"] == row_id]

    def records(self, row_id: str) -> list[dict]:
        return read_csv(self.processed / f"records_{row_id}.csv")


def _copy_preset_dq_rows(source: Path, target: Path) -> None:
    """Seed the fixture log with the preset rows of the repository log only (D-061, defect 3).

    The repository log is the single data-quality file (D-040) and carries the
    rows of real runs; those rows must not leak into offline assertions.
    """
    import csv
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [r for r in reader if r.get("origin") == "preset"]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_full_pipeline(tmp_path: Path, transport=None, cutoff: str = "2026-09-30", expect_incomplete: bool = False,
                      with_figures: bool = True) -> PipelineOutputs:
    import shutil
    from src.extract import crossref_peer_reviews, crossref_works, sciety_evaluations
    from src.extract.crossref_common import ExtractionIncomplete
    from src.normalise import clean_and_normalise
    from src.analyse import build_aggregates

    run_config, sources, platforms, logger, roots = run_context(tmp_path, cutoff)
    transport = transport or FixtureTransport()
    error: Exception | None = None
    for module in (crossref_works, crossref_peer_reviews, sciety_evaluations):
        try:
            module.run(run_config, sources, platforms, logger, transport=transport, sleeper=lambda _: None, **roots)
        except ExtractionIncomplete as exc:
            error = exc
            if not expect_incomplete:
                raise
    processed, tables, figures = tmp_path / "processed", tmp_path / "tables", tmp_path / "figures"
    processed.mkdir(parents=True, exist_ok=True)
    _copy_preset_dq_rows(REPO_ROOT / "data" / "processed" / "data_quality_log.csv", processed / "data_quality_log.csv")
    clean_and_normalise.run(run_config, sources, platforms, logger, interim_root=roots["interim_root"],
                            manifest_root=roots["manifest_root"], processed_root=processed)
    manifest = build_aggregates.run(run_config, sources, platforms, logger, processed_root=processed,
                                    manifest_root=roots["manifest_root"], tables_root=tables)
    checksums = tmp_path / "CHECKSUMS.txt"
    if with_figures:
        from src.report import make_reports
        make_reports.run(run_config, sources, platforms, logger, processed_root=processed, tables_root=tables,
                         figures_root=figures, checksums_path=checksums)
    return PipelineOutputs(tmp_path, run_config, platforms, roots, processed, tables, figures, checksums, error,
                           manifest)
