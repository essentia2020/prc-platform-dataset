"""OpenAlex diagnostics (D-041, D-066) РІР‚вЂќ a stage after ``analyse``.

OpenAlex is a diagnostic source only.  This stage reads
``data/processed/works_included.csv`` and writes rows to
``data/processed/data_quality_log.csv``; nothing it retrieves enters a
record file, ``works_included.csv``, a table or a figure.

Two diagnostics are produced per run:

* ``openalex_volume_check`` РІР‚вЂќ for every quantified Crossref row, the DOIs
  of the included works are resolved in OpenAlex (``filter=doi:a|b|РІР‚В¦``,
  at most ``per_request_cap`` DOIs per request) and compared with the row
  series per counting year; where ``config/sources.yaml`` lists an OpenAlex
  source id for the row, the source's own yearly work counts are retrieved
  as well (one ``group_by=publication_year`` request).  One row per
  register row; ``n_records_affected`` = included works not found in
  OpenAlex.
* ``openalex_pair_signal`` РІР‚вЂќ for the preprint/article pair named in the
  configuration (VeriXiv / Gates Open Research), included works that carry
  no Crossref correspondence (empty ``correspondence_basis``) are matched on
  their OpenAlex work id.  One row; ``n_records_affected`` = number of
  pairs; the DOI pairs are listed in ``description``.  The pair is never
  added to ``cross_platform_overlap.csv``.

Every request and response is stored immutably under
``data/raw/openalex/<scope>/<run_id>/<walk_id>/`` (D-031) and listed in a
walk manifest; a complete walk of the same run is reused, so a re-run of
the stage costs no API calls.  The API key is read from the environment
variable named in the configuration, sent in a header, and never written
to a sidecar, a manifest or a log.  A failed or capped walk yields no row
(a diagnostic never blocks a row, D-037); the outcome is recorded under
``openalex_diagnostics`` in the run manifest.

Run order: ``analyse`` replaces every run row of its ``run_id`` in the
data-quality log, so this stage must run after ``analyse`` (and again
after any re-run of ``analyse``); it replaces only its own rows.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, quote, urlsplit

from ..analyse.build_aggregates import DQ_COLUMNS
from ..common.config import ConfigError, RunConfig
from ..common.http import Attempt, PoliteClient, default_transport
from ..common.interim import read_csv, write_csv
from ..common.manifest import (PageEntry, WalkManifestWriter, list_walks, run_manifest_path, select_walk,
                               update_run_manifest_field, utc_now, walk_manifest_path)
from ..common.raw_store import RawStore, resolve_raw_root
from .crossref_common import http_settings

SOURCE = "openalex"
STAGE = "openalex_diagnostics"
ISSUE_VOLUME_CHECK = "openalex_volume_check"
ISSUE_PAIR_SIGNAL = "openalex_pair_signal"
ISSUE_TYPES = (ISSUE_VOLUME_CHECK, ISSUE_PAIR_SIGNAL)
ISSUE_ID_TAG = "oa"                      # DQ-<run_id>-oa-<nnn>, disjoint from the analyse numbering
RULE_BATCHES = "openalex_batches_exhausted"
RULE_GROUP_BY = "openalex_group_by_single_page"
REDACTED = "<redacted>"
DEFAULT_MANIFEST_ROOT = Path("data") / "manifests"
DEFAULT_PROCESSED_ROOT = Path("data") / "processed"
EFFECT = "none (diagnostic)"


class OpenAlexConfigError(ConfigError):
    pass


class BudgetExhausted(RuntimeError):
    pass


# ------------------------------------------------------------------ config
def openalex_settings(sources_config: Mapping[str, Any]) -> dict[str, Any]:
    """The validated ``sources.openalex`` block."""
    block = (sources_config.get("sources") or {}).get(SOURCE)
    if not isinstance(block, Mapping):
        raise OpenAlexConfigError("config/sources.yaml: source 'openalex' is not declared")
    for key in ("base_url", "auth", "query_templates", "per_request_cap", "rate_limit", "budget", "role",
                "licence", "terms_url", "pair_signal"):
        if key not in block:
            raise OpenAlexConfigError(f"config/sources.yaml: source 'openalex' lacks field {key!r}")
    if block["role"] != "diagnostic":
        raise OpenAlexConfigError("config/sources.yaml: openalex.role must be 'diagnostic' (D-041, D-066)")
    for key in ("api_key_env", "header", "header_value_template"):
        if key not in block["auth"]:
            raise OpenAlexConfigError(f"config/sources.yaml: openalex.auth lacks field {key!r}")
    for key in ("works_by_doi", "source_years"):
        if key not in block["query_templates"]:
            raise OpenAlexConfigError(f"config/sources.yaml: openalex.query_templates lacks {key!r}")
    cap = int(block["per_request_cap"])
    if not 1 <= cap <= 100:
        raise OpenAlexConfigError("config/sources.yaml: openalex.per_request_cap must be between 1 and 100")
    if int(block["budget"].get("max_requests_per_run") or 0) < 1:
        raise OpenAlexConfigError("config/sources.yaml: openalex.budget.max_requests_per_run must be >= 1")
    for key in ("preprint_row", "article_row"):
        if not block["pair_signal"].get(key):
            raise OpenAlexConfigError(f"config/sources.yaml: openalex.pair_signal lacks {key!r}")
    return dict(block)


def read_api_key(settings: Mapping[str, Any], explicit: str | None = None,
                 environ: Mapping[str, str] | None = None) -> str:
    """The API key from the environment variable named in the configuration."""
    if explicit:
        return explicit
    name = str(settings["auth"]["api_key_env"])
    value = (environ if environ is not None else os.environ).get(name, "").strip()
    if not value:
        raise OpenAlexConfigError(f"OpenAlex API key not set: export {name} before running the stage "
                                  "(the key is never read from a tracked file)")
    return value


def build_client(run_config: RunConfig, sources_config: Mapping[str, Any], api_key: str, *,
                 transport=None, sleeper=None, logger=None) -> PoliteClient:
    settings = http_settings(run_config, sources_config, SOURCE)
    source = openalex_settings(sources_config)
    per_second = float((source.get("rate_limit") or {}).get("max_requests_per_second") or 1)
    header = str(source["auth"]["header"])
    value = str(source["auth"]["header_value_template"]).format(key=api_key)
    kwargs: dict[str, Any] = dict(
        user_agent=run_config.user_agent(), timeout_seconds=float(settings["timeout_seconds"]),
        max_attempts_per_page=int(settings["max_attempts_per_page"]),
        backoff_seconds=[float(b) for b in settings["backoff_seconds"]],
        min_interval_seconds=1.0 / per_second if per_second > 0 else 1.0,
        accept=str(settings["accept"]), transport=transport or default_transport, logger=logger,
        secret_headers={header: value})
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    return PoliteClient(**kwargs)


# --------------------------------------------------------------- utilities
def normalise_doi(value: str) -> str:
    text = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text

def _lookup_doi(work: Mapping[str, str]) -> str:
    """DOI resolved in OpenAlex: the counting record's own DOI (version suffix
    included), falling back to the canonical work DOI when the record id is
    empty or not a DOI. OpenAlex has no record for a version-stripped stem."""
    for key in ("counting_record_id", "posting_record_id", "work_doi"):
        value = normalise_doi(work.get(key, ""))
        if value and value.startswith("10."):
            return value
    return ""

def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _json_results(body: bytes) -> str | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any decode failure is a rejection reason
        return f"not JSON ({type(exc).__name__})"
    if not isinstance(payload, Mapping):
        return "JSON body is not an object"
    if "results" not in payload and "group_by" not in payload:
        return "JSON body has neither 'results' nor 'group_by'"
    return None


def _source_id_of(work: Mapping[str, Any]) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    ident = str(source.get("id") or "")
    return ident.rsplit("/", 1)[-1] if ident else ""


def parse_works(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """``doi -> {id, publication_year, source_id}`` from one ``/works`` page."""
    found: dict[str, dict[str, Any]] = {}
    for work in payload.get("results") or []:
        doi = normalise_doi(str(work.get("doi") or ""))
        if not doi:
            continue
        found[doi] = {"id": str(work.get("id") or "").rsplit("/", 1)[-1],
                      "publication_year": work.get("publication_year"),
                      "source_id": _source_id_of(work)}
    return found


def parse_group_by(payload: Mapping[str, Any]) -> dict[str, int]:
    """``year -> count`` from one ``group_by=publication_year`` page."""
    counts: dict[str, int] = {}
    for group in payload.get("group_by") or []:
        key = str(group.get("key") or "")
        if key.isdigit():
            counts[key] = int(group.get("count") or 0)
    return counts


@dataclass
class Budget:
    cap: int
    used: int = 0

    def take(self) -> None:
        if self.used >= self.cap:
            raise BudgetExhausted(f"request cap {self.cap} reached")
        self.used += 1


@dataclass
class WalkOutcome:
    scope: str
    walk_id: str
    state: str                     # complete / failed / reused
    reason: str = ""
    pages: int = 0
    requests: int = 0
    sha256: list[str] = field(default_factory=list)
    payloads: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.state in ("complete", "reused")


# ------------------------------------------------------------- the fetcher
class ScopeFetcher:
    """Fetch the pages of one diagnostic scope as one walk, or reuse a complete walk."""

    def __init__(self, *, client: PoliteClient, store: RawStore, manifest_root: Path, run_id: str,
                 policy: str, budget: Budget, logger=None, force_new_walk: bool = False) -> None:
        self.client, self.store, self.manifest_root = client, store, manifest_root
        self.run_id, self.policy, self.budget, self.logger = run_id, policy, budget, logger
        self.force_new_walk = force_new_walk

    def _log(self, kind: str, **payload) -> None:
        if self.logger is not None:
            self.logger.event(kind, source=SOURCE, **payload)

    def _reuse(self, scope: str) -> WalkOutcome | None:
        walks = list_walks(self.manifest_root, self.run_id, SOURCE, scope)
        selected, reason = select_walk(walks, self.policy) if walks else (None, "no walks")
        if selected is None or self.force_new_walk:
            return None
        payloads = [self.store.read_response_json(p.response_path) for p in selected.pages]
        self._log("openalex_walk_reused", scope=scope, walk_id=selected.walk_id, reason=reason)
        return WalkOutcome(scope, selected.walk_id, "reused", reason, len(selected.pages), 0,
                           [p.sha256 for p in selected.pages], payloads)

    def _persist(self, scope: str, walk_id: str, page: int, writer: WalkManifestWriter,
                 label: str) -> Callable[[Attempt], None]:
        secret = self.client.secret_header_names

        def on_attempt(attempt: Attempt) -> None:
            request = {**attempt.request_record, "run_id": self.run_id, "walk_id": walk_id, "source": SOURCE,
                       "scope": scope, "page": page, "cursor_in": label,
                       "headers": {**self.client.headers, **{name: REDACTED for name in secret}},
                       "auth": f"header {', '.join(secret)} ({REDACTED})",
                       "response_status": attempt.status, "response_headers": attempt.headers,
                       "error": attempt.error, "parameters": parse_qs(urlsplit(attempt.url).query)}
            paths = self.store.write_attempt(SOURCE, scope, self.run_id, walk_id, page, attempt.number,
                                             request, attempt.body)
            digest = self.store.file_sha256(paths.response_rel)
            attempt.stored_response_rel, attempt.stored_sha256 = paths.response_rel, digest
            if not attempt.accepted:
                writer.reject_attempt(page, attempt.number, attempt.status, attempt.rejection_reason,
                                      paths.response_rel, digest)
        return on_attempt

    def fetch(self, scope: str, urls: list[tuple[str, str]], rule: str, **completion_extra) -> WalkOutcome:
        """``urls`` = ``[(label, url), РІР‚В¦]`` РІР‚вЂќ one page per entry."""
        reused = self._reuse(scope)
        if reused is not None:
            return reused
        known = [w.walk_id for w in list_walks(self.manifest_root, self.run_id, SOURCE, scope)]
        walk_id = self.store.new_walk_id(SOURCE, scope, self.run_id, known)
        writer = WalkManifestWriter(walk_manifest_path(self.manifest_root, self.run_id, SOURCE, scope, walk_id),
                                    self.run_id, SOURCE, scope, walk_id)
        outcome = WalkOutcome(scope, walk_id, "in_progress")
        items_total = 0
        for page, (label, url) in enumerate(urls, start=1):
            try:
                self.budget.take()
            except BudgetExhausted as exc:
                writer.close("failed", reason=str(exc), pages_accepted=page - 1, items_total=items_total)
                outcome.state, outcome.reason = "failed", str(exc)
                self._log("openalex_walk_failed", scope=scope, walk_id=walk_id, reason=str(exc))
                return outcome
            outcome.requests += 1
            result = self.client.get_page(url, _json_results, self._persist(scope, walk_id, page, writer, label))
            outcome.requests += len(result.attempts) - 1
            accepted = result.accepted
            if accepted is None:
                reason = result.attempts[-1].rejection_reason if result.attempts else "no attempt"
                writer.close("failed", reason=f"page {page}: {reason}", pages_accepted=page - 1,
                             items_total=items_total)
                outcome.state, outcome.reason = "failed", f"page {page}: {reason}"
                self._log("openalex_walk_failed", scope=scope, walk_id=walk_id, reason=outcome.reason)
                return outcome
            payload = json.loads(accepted.body.decode("utf-8"))
            items = len(payload.get("results") or payload.get("group_by") or [])
            items_total += items
            writer.accept_page(PageEntry(page, accepted.number, accepted.stored_response_rel, accepted.stored_sha256,
                                         len(accepted.body), accepted.status or 0, label, "", items, utc_now()))
            outcome.pages += 1
            outcome.sha256.append(accepted.stored_sha256)
            outcome.payloads.append(payload)
        writer.close("complete", reason="all pages accepted", pages_accepted=outcome.pages, items_total=items_total,
                     completion={"rule": rule, "pages": len(urls), "items_total": items_total, **completion_extra})
        outcome.state = "complete"
        self._log("openalex_walk_complete", scope=scope, walk_id=walk_id, pages=outcome.pages)
        return outcome


# ------------------------------------------------------------- the stage
def _works_by_row(processed_root: Path) -> dict[str, list[dict[str, str]]]:
    path = processed_root / "works_included.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run the analyse stage first")
    by_row: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(path):
        if row.get("included") == "true":
            by_row[row["row_id"]].append(row)
    return by_row


def _crossref_rows(platforms: list[Mapping[str, Any]]) -> list[str]:
    return [str(p["row_id"]) for p in platforms
            if p.get("register_status") == "quantified" and p.get("data_source") in ("crossref", "both")]


def _works_url(settings: Mapping[str, Any], dois: list[str]) -> str:
    template = str(settings["query_templates"]["works_by_doi"])
    joined = "|".join(quote(d, safe="/:()<>;") for d in dois)
    return str(settings["base_url"]).rstrip("/") + template.format(dois=joined, per_page=int(settings["per_request_cap"]))


def _source_url(settings: Mapping[str, Any], source_id: str, year_from: int, year_to: int) -> str:
    template = str(settings["query_templates"]["source_years"])
    return str(settings["base_url"]).rstrip("/") + template.format(source_id=source_id, year_from=year_from,
                                                                    year_to=year_to)


def _year_summary(works: list[dict[str, str]], found: Mapping[str, Mapping[str, Any]],
                  source_years: Mapping[str, int] | None) -> str:
    row_years = Counter(w["counting_year"] for w in works)
    parts = []
    for year in sorted(row_years):
        in_year = [w for w in works if w["counting_year"] == year]
        resolved = [found[_lookup_doi(w)] for w in in_year if _lookup_doi(w) in found]
        agree = sum(1 for r in resolved if str(r.get("publication_year") or "") == year)
        text = f"{year}: row={len(in_year)} found={len(resolved)} year_agree={agree}"
        if source_years is not None:
            text += f" source={source_years.get(year, 0)}"
        parts.append(text)
    return "; ".join(parts)


def _dq_row(run_id: str, number: int, row_id: str, issue_type: str, description: str, evidence: str,
            handling: str, n: int, walks: str) -> dict[str, str]:
    return {"issue_id": f"DQ-{run_id}-{ISSUE_ID_TAG}-{number:03d}", "row_id": row_id, "issue_type": issue_type,
            "description": description, "evidence": evidence, "effect_on_counts": EFFECT, "handling": handling,
            "n_records_affected": str(n), "status": "observed", "origin": "run", "run_id": run_id, "walk_id": walks}


def write_diagnostic_rows(path: Path, run_id: str, new_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Replace this stage's rows of ``run_id``; every other row is kept byte for byte."""
    existing = [dict(r) for r in read_csv(path)] if path.exists() else []
    for r in existing:
        r.setdefault("origin", "preset")
        r.setdefault("run_id", "")
        r.setdefault("walk_id", "")
    kept = [r for r in existing
            if not (r.get("origin") == "run" and r.get("run_id") == run_id and r.get("issue_type") in ISSUE_TYPES)]
    rows = kept + new_rows
    write_csv(path, DQ_COLUMNS, rows)
    return rows


def run(run_config: RunConfig, sources_config: Mapping[str, Any], platforms: list[Mapping[str, Any]], logger,
        *, processed_root: Path | None = None, manifest_root: Path | None = None, raw_root=None,
        transport=None, sleeper=None, api_key: str | None = None, force_new_walk: bool = False,
        **_ignored) -> dict[str, Any]:
    settings = openalex_settings(sources_config)
    key = read_api_key(settings, api_key)
    processed = Path(processed_root or DEFAULT_PROCESSED_ROOT)
    manifests = Path(manifest_root or DEFAULT_MANIFEST_ROOT)
    store = RawStore(resolve_raw_root(raw_root))
    client = build_client(run_config, sources_config, key, transport=transport, sleeper=sleeper, logger=logger)
    budget = Budget(int(settings["budget"]["max_requests_per_run"]))
    fetcher = ScopeFetcher(client=client, store=store, manifest_root=manifests, run_id=run_config.run_id,
                           policy=run_config.selected_walk_policy, budget=budget, logger=logger,
                           force_new_walk=force_new_walk)
    cap = int(settings["per_request_cap"])
    source_ids = {str(k): str(v) for k, v in (settings.get("source_ids") or {}).items() if v}
    works_by_row = _works_by_row(processed)
    rows_out: list[dict[str, str]] = []
    record: dict[str, Any] = {"stage": STAGE, "role": "diagnostic", "scopes": {}, "rows_written": 0,
                              "requests_used": 0, "request_cap": budget.cap, "recorded_at": utc_now()}
    resolved_by_row: dict[str, dict[str, dict[str, Any]]] = {}
    counter = 0

    def note(outcome: WalkOutcome) -> None:
        record["scopes"][outcome.scope] = {"walk_id": outcome.walk_id, "state": outcome.state,
                                           "reason": outcome.reason, "pages": outcome.pages,
                                           "requests": outcome.requests, "sha256": outcome.sha256}

    # (a) volume check --------------------------------------------------------
    for row_id in _crossref_rows(platforms):
        works = works_by_row.get(row_id, [])
        dois = sorted({_lookup_doi(w) for w in works if _lookup_doi(w)})
        if not dois:
            continue
        urls = [(f"batch:{i}", _works_url(settings, batch)) for i, batch in enumerate(chunks(dois, cap), start=1)]
        outcome = fetcher.fetch(f"works_by_doi__{row_id}", urls, RULE_BATCHES, dois_requested=len(dois))
        note(outcome)
        if not outcome.ok:
            continue
        requested = set(dois)
        returned: dict[str, dict[str, Any]] = {}
        for payload in outcome.payloads:
            returned.update(parse_works(payload))
        found = {d: v for d, v in returned.items() if d in requested}
        other_doi = len(returned) - len(found)
        resolved_by_row[row_id] = found
        source_years: dict[str, int] | None = None
        walks = f"works_by_doi__{row_id}={outcome.walk_id}"
        if row_id in source_ids:
            years = sorted(int(w["counting_year"]) for w in works if w["counting_year"].isdigit())
            s_outcome = fetcher.fetch(f"source_years__{row_id}",
                                      [("group_by:publication_year",
                                        _source_url(settings, source_ids[row_id], years[0], years[-1]))],
                                      RULE_GROUP_BY, source_id=source_ids[row_id])
            note(s_outcome)
            if s_outcome.ok:
                source_years = parse_group_by(s_outcome.payloads[0])
                walks += f"; source_years__{row_id}={s_outcome.walk_id}"
        missing = len(dois) - len(found)
        counter += 1
        head = (f"OpenAlex volume check: {len(dois)} included works resolved by DOI, {len(found)} found, "
                f"{missing} not found")
        if other_doi:
            head += (f"; OpenAlex answered with {len(returned)} distinct works, {other_doi} of them under a "
                     f"different primary DOI (OpenAlex keeps one record per work and lists the requested DOI "
                     f"as an alternate identifier; counted as not found)")
        if row_id in source_ids:
            head += (f"; source {source_ids[row_id]} yearly counts "
                     + ("retrieved" if source_years is not None else "not retrieved (walk failed)"))
        rows_out.append(_dq_row(run_config.run_id, counter, row_id, ISSUE_VOLUME_CHECK,
                                head + ". Per counting year: " + _year_summary(works, found, source_years) + ".",
                                f"data/raw/openalex/works_by_doi__{row_id}/{run_config.run_id}/{outcome.walk_id}",
                                "Diagnostic only; no series, coverage status or register field is changed (D-066).",
                                missing, walks))

    # (b) pair signal ---------------------------------------------------------
    pair = settings["pair_signal"]
    pre_row, art_row = str(pair["preprint_row"]), str(pair["article_row"])
    if pre_row in resolved_by_row and art_row in resolved_by_row:
        def residual(row_id: str) -> dict[str, str]:
            return {_lookup_doi(w): resolved_by_row[row_id].get(_lookup_doi(w), {}).get("id", "")
                    for w in works_by_row.get(row_id, []) if not (w.get("correspondence_basis") or "").strip()}
        pre, art = residual(pre_row), residual(art_row)
        by_id: dict[str, list[str]] = defaultdict(list)
        for doi, ident in art.items():
            if ident:
                by_id[ident].append(doi)
        pairs = sorted((p_doi, a_doi) for p_doi, ident in pre.items() if ident for a_doi in by_id.get(ident, []))
        counter += 1
        listed = ", ".join(f"{p}={a}" for p, a in pairs) if pairs else "none"
        rows_out.append(_dq_row(
            run_config.run_id, counter, art_row, ISSUE_PAIR_SIGNAL,
            f"OpenAlex pair signal for {pre_row}/{art_row}: {len(pre)} residual {pre_row} works and {len(art)} "
            f"residual {art_row} works (included, empty correspondence_basis) resolved; {len(pairs)} pair(s) share "
            f"one OpenAlex work id. Pairs ({pre_row}={art_row}): {listed}.",
            f"data/raw/openalex/works_by_doi__{pre_row}/{run_config.run_id}; "
            f"data/raw/openalex/works_by_doi__{art_row}/{run_config.run_id}",
            "Signal only; not added to cross_platform_overlap.csv, correspondence_basis keeps Crossref values (D-041).",
            len(pairs), f"works_by_doi__{pre_row}={record['scopes'][f'works_by_doi__{pre_row}']['walk_id']}; "
                        f"works_by_doi__{art_row}={record['scopes'][f'works_by_doi__{art_row}']['walk_id']}"))

    # write -------------------------------------------------------------------
    rows = write_diagnostic_rows(processed / "data_quality_log.csv", run_config.run_id, rows_out)
    record["rows_written"] = len(rows_out)
    record["requests_used"] = budget.used
    manifest_file = run_manifest_path(manifests, run_config.run_id)
    if manifest_file.exists():
        update_run_manifest_field(manifest_file, run_id=run_config.run_id, key=STAGE, value=record)
    if logger is not None:
        logger.event("openalex_diagnostics_end", rows_written=len(rows_out), requests_used=budget.used,
                     scopes=len(record["scopes"]))
    return {"rows": rows_out, "log_rows": rows, "record": record}
