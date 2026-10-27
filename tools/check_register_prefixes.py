#!/usr/bin/env python3
"""One-off register check: do the declared Crossref scopes match the owner prefixes?

For every quantified Crossref row the check resolves the sample DOIs declared
in ``extraction_selector.crossref`` (``sample_work_doi``, ``sample_review_doi``)
through ``GET /works/<doi>`` and compares the returned owner ``prefix`` (and
``member``) with the scopes the row declares: work prefixes / ISSN scopes for
the work DOI, ``review_prefixes()`` for the review DOI.  A DOI whose owner
prefix is not among the declared scopes is a mismatch — the kind that produced
three silent gaps in run_20261026_01 (MedEdPublish → 10.12688, Open Research
Europe → 10.68336, NIHR Open Research → 10.3310).  Rows without sample DOIs are
reported as ``unchecked`` so the gap in the declaration is visible too.

This script is run only locally by the maintainer before an extraction; it is
the only module besides the extraction stage that contacts api.crossref.org,
and it does so solely when invoked.  Nothing in the test suite calls the
network: tests inject a fixture transport.

Usage::

    python tools/check_register_prefixes.py                 # text report
    python tools/check_register_prefixes.py --json          # machine-readable
    python tools/check_register_prefixes.py --rows nihr_open_research open_research_europe

Exit status: 0 when no mismatch was found, 1 when at least one row mismatches,
2 when a sample DOI could not be resolved (HTTP error) so the check is
inconclusive for that row.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_run_config, load_sources_config  # noqa: E402
from src.common.http import default_transport  # noqa: E402
from src.common.identifiers import collapse_repeated_slashes, normalise_doi  # noqa: E402
from src.common.register import load_platforms  # noqa: E402
from src.extract.selectors import CrossrefSelector, crossref_selectors  # noqa: E402

Transport = Callable[[str, dict[str, str], float], tuple[int, Mapping[str, str], bytes]]


@dataclass
class DoiCheck:
    role: str                 # "work" / "review"
    doi: str
    status: str               # ok / mismatch / unresolved / unchecked
    http_status: int | None = None
    owner_prefix: str = ""
    member: str = ""
    record_type: str = ""
    issns: list[str] = field(default_factory=list)
    declared: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class RowCheck:
    row_id: str
    checks: list[DoiCheck]

    @property
    def status(self) -> str:
        statuses = {c.status for c in self.checks}
        if "mismatch" in statuses:
            return "mismatch"
        if "unresolved" in statuses:
            return "unresolved"
        if statuses == {"unchecked"} or statuses == {"unchecked", "not_applicable"}:
            return "unchecked"
        return "ok"


def _works_url(base_url: str, doi: str, mailto: str) -> str:
    quoted = urllib.parse.quote(doi, safe="")
    return f"{base_url.rstrip('/')}/works/{quoted}?mailto={urllib.parse.quote(mailto, safe='@')}"


RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_WAITS = (2.0, 5.0, 15.0)      # seconds between attempts; the REST API throttles bursts of lookups
REQUEST_SPACING = 1.0               # minimum pause between lookups


def _resolve(transport: Transport, url: str, headers: dict[str, str], timeout: float,
             sleep: Callable[[float], None] = time.sleep) -> tuple[int, Mapping[str, Any] | None]:
    status, _, body = transport(url, headers, timeout)
    for wait in RETRY_WAITS:
        if status not in RETRY_STATUSES:
            break
        sleep(wait)
        status, _, body = transport(url, headers, timeout)
    if status != 200:
        return status, None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None
    message = payload.get("message") if isinstance(payload, Mapping) else None
    return status, message if isinstance(message, Mapping) else None


def check_selector(sel: CrossrefSelector, transport: Transport, *, base_url: str, mailto: str,
                   user_agent: str, timeout: float = 30.0, sleep: Callable[[float], None] = time.sleep) -> RowCheck:
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    checks: list[DoiCheck] = []
    samples = (("work", sel.sample_work_doi, sel.work_keys()),
               ("review", sel.sample_review_doi, sel.review_prefixes()))
    for role, raw, declared in samples:
        if role == "review" and not sel.record_types_include_evaluations():
            continue
        if role == "work" and sel.target_filter == "external" and not raw:
            # the row's works are the external targets of its evaluation records; no owner prefix to compare
            checks.append(DoiCheck(role, "", "not_applicable", declared=list(declared),
                                   note="works are external to the row's scopes (target_filter: external)"))
            continue
        if not raw:
            checks.append(DoiCheck(role, "", "unchecked", declared=list(declared),
                                   note=f"no sample_{role}_doi declared"))
            continue
        doi = collapse_repeated_slashes(normalise_doi(raw))
        http_status, message = _resolve(transport, _works_url(base_url, doi, mailto), headers, timeout, sleep)
        sleep(REQUEST_SPACING)
        if message is None:
            why = ("not found (HTTP 404)" if http_status == 404 else
                   f"HTTP {http_status} after {len(RETRY_WAITS)} retries" if http_status in RETRY_STATUSES else
                   f"HTTP {http_status}")
            checks.append(DoiCheck(role, doi, "unresolved", http_status=http_status, declared=list(declared),
                                   note=f"DOI did not resolve in the Crossref REST API: {why}"))
            continue
        owner = str(message.get("prefix") or "")
        issns = [str(i) for i in (message.get("ISSN") or [])]
        matched = owner in declared or any(f"issn:{i}" in declared for i in issns)
        check = DoiCheck(role, doi, "ok" if matched else "mismatch", http_status=http_status, owner_prefix=owner,
                         member=str(message.get("member") or ""), record_type=str(message.get("type") or ""),
                         issns=issns, declared=list(declared))
        if not matched:
            check.note = (f"owner prefix {owner} (member {check.member}) is not among the declared scopes; "
                          f"the {role} records of this row are invisible to the current walks")
        checks.append(check)
    return RowCheck(sel.row_id, checks)


def run_check(rows: Iterable[Mapping[str, Any]], transport: Transport = default_transport, *,
              base_url: str, mailto: str, user_agent: str, only: set[str] | None = None,
              sleep: Callable[[float], None] = time.sleep) -> list[RowCheck]:
    out: list[RowCheck] = []
    for sel in crossref_selectors(rows):
        if only and sel.row_id not in only:
            continue
        row = next(r for r in rows if r["row_id"] == sel.row_id)
        if row.get("register_status") != "quantified":
            continue
        out.append(check_selector(sel, transport, base_url=base_url, mailto=mailto, user_agent=user_agent,
                                  sleep=sleep))
    return out


def format_report(results: list[RowCheck]) -> str:
    lines = ["row_id | role | sample DOI | owner prefix | member | declared scopes | status"]
    for r in results:
        for c in r.checks:
            lines.append(f"{r.row_id} | {c.role} | {c.doi or '-'} | {c.owner_prefix or '-'} | {c.member or '-'} | "
                         f"{','.join(c.declared) or '-'} | {c.status}" + (f" — {c.note}" if c.note else ""))
    summary = {s: sum(1 for r in results if r.status == s) for s in ("ok", "mismatch", "unresolved", "unchecked")}
    lines.append("")
    lines.append("rows: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    return "\n".join(lines)


def exit_code(results: list[RowCheck]) -> int:
    statuses = {r.status for r in results}
    if "mismatch" in statuses:
        return 1
    if "unresolved" in statuses:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--rows", nargs="*", default=None, help="restrict to these row ids")
    args = parser.parse_args(argv)
    run_config = load_run_config()
    sources = load_sources_config()
    base_url = str(sources["sources"]["crossref"]["base_url"])
    results = run_check(load_platforms(), base_url=base_url, mailto=run_config.mailto,
                        user_agent=run_config.user_agent(), only=set(args.rows) if args.rows else None)
    if args.json:
        print(json.dumps([{"row_id": r.row_id, "status": r.status, "checks": [asdict(c) for c in r.checks]}
                          for r in results], indent=2))
    else:
        print(format_report(results))
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
