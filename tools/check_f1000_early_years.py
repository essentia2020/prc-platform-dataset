#!/usr/bin/env python3
"""Read-only reconciliation of early F1000Research dates and DQ-018 raw counts.

Run from the repository after the local rebuild:
  python tools/check_f1000_early_years.py --raw-root <raw store root>

Print JSON to stdout (redirect to a file if desired). No network calls or
dataset writes. Accepted page attempts only, with manifest SHA-256 checks.
The cited historical w01 is inspected even if failed, labelled as such and
never treated as the selected complete walk. Missing inputs exit 2.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.common.dates import format_partial_date, parse_crossref_date
from src.common.identifiers import canonical_doi, normalise_doi
from src.common.manifest import read_walk_manifest
from src.common.raw_store import RawStore
from src.common.register import load_platforms
from src.extract.selectors import crossref_selectors

ROW = "f1000research"
SCOPE = "works__10.12688__journal-article"
VOLUME_NUMBER = re.compile(r"^10\.12688/f1000research\.\d+-\d+\.v\d+$")


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def year_dois(records, year):
    return {r["doi"] for r in records if r["issued"][:4] == str(year)}


def population(records, version_pattern):
    """Separate record occurrences, distinct version DOIs and canonical works."""
    return {
        "record_lines": len(records),
        "distinct_dois": len({r["doi"] for r in records}),
        "distinct_canonical_work_ids": len({
            canonical_doi(r["doi"], version_pattern) for r in records}),
    }


def raw_records(manifest, store, selector):
    walk = read_walk_manifest(manifest)
    records = []
    for page in walk.pages:
        if store.file_sha256(page.response_path) != page.sha256:
            raise ValueError(f"SHA-256 mismatch: {page.response_path}")
        payload = store.read_response_json(page.response_path)
        for item in payload["message"]["items"]:
            if selector.matches_work(item):
                records.append({
                    "doi": normalise_doi(item["DOI"]),
                    "issued": format_partial_date(parse_crossref_date(item.get("issued"))),
                    "page": page.page, "accepted_attempt": page.accepted_attempt,
                })
    return walk, records


def reconcile_year(records, works, year):
    """All record-year works vs the selected work event, without guessing causes."""
    issued_records = [r for r in records if r["issued"][:4] == str(year)]
    roles = Counter(r["row_entity_type"] for r in issued_records)
    ids = {r["canonical_work_id"] for r in issued_records}
    by_work = defaultdict(list)
    for record in records:
        if record["row_entity_type"] == "work_record":
            by_work[record["canonical_work_id"]].append(record)
    candidates = {key: rs for key, rs in by_work.items()
                  if any(r["issued"][:4] == str(year) for r in rs)}
    outcomes, exceptions = Counter(), []
    for key, rs in sorted(candidates.items()):
        work = works.get(key)
        counted = bool(work and work["included"] == "true"
                       and work["in_eligible_range"] == "true")
        outcome = ("missing_work_row" if work is None else
                   f"included={work['included']}; in_eligible_range={work['in_eligible_range']}; "
                   f"counting_year={work['counting_year']}; exclusion_reason={work['exclusion_reason']}")
        outcomes[outcome] += 1
        if not work or work["counting_year"] != str(year) or work["included"] != "true":
            exceptions.append({
                "canonical_work_id": key, "counted": counted,
                "work": {k: work[k] for k in (
                    "included", "in_eligible_range", "counting_year", "exclusion_reason",
                    "counting_record_id", "counting_event_date_raw",
                    "date_order_ambiguous", "tie_break_source")} if work else None,
                "records": [{k: r[k] for k in (
                    "source_record_id", "issued", "event_date_raw", "record_flag",
                    "exclusion_reason", "title")} for r in rs],
            })
    return {"all_record_lines": len(issued_records),
            "record_lines_by_entity_type": dict(sorted(roles.items())),
            "distinct_ids_including_blank_all_records": len(ids),
            "blank_canonical_id_lines": sum(not r["canonical_work_id"] for r in issued_records),
            "record_lines": sum(r["issued"][:4] == str(year)
                               for rs in candidates.values() for r in rs),
            "distinct_canonical_work_ids": len(candidates),
            "outcomes": dict(sorted(outcomes.items())), "exceptions": exceptions}


def compare(raw, interim, records, version_pattern):
    volume_number = [r for r in raw if VOLUME_NUMBER.match(r["doi"])]
    raw2012 = year_dois(volume_number, 2012)
    interim2012 = year_dois(interim, 2012)
    processed2012 = {normalise_doi(r["work_doi"]) for r in records
                     if r["row_entity_type"] == "work_record" and r["issued"][:4] == "2012"}
    all_interim = {r["doi"] for r in interim}
    return {
        "volume_number_all_years": population(volume_number, version_pattern),
        "volume_number_by_issued_year": {
            year: population([r for r in volume_number if r["issued"][:4] == year], version_pattern)
            for year in sorted({r["issued"][:4] for r in volume_number})},
        "raw_2012_duplicate_dois": {doi: n for doi, n in sorted(Counter(
            r["doi"] for r in volume_number if r["issued"][:4] == "2012").items()) if n > 1},
        "raw_2012_not_in_interim_any_year": sorted(raw2012 - all_interim),
        "raw_2012_in_interim_but_not_issued_2012": sorted((raw2012 & all_interim) - interim2012),
        "interim_2012_not_in_this_raw_volume_number_2012": sorted(interim2012 - raw2012),
        "interim_2012_not_in_processed_2012": sorted(interim2012 - processed2012),
        "processed_2012_not_in_interim_2012": sorted(processed2012 - interim2012),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, help="Defaults to PRC_RAW_STORE or data/raw")
    parser.add_argument("--run", default="run_20261102_01")
    parser.add_argument("--manifest-root", type=Path, default=REPO / "data/manifests")
    parser.add_argument("--processed-root", type=Path, default=REPO / "data/processed")
    parser.add_argument("--interim-root", type=Path, default=REPO / "data/interim")
    args = parser.parse_args(argv)
    try:
        platform = next(r for r in load_platforms() if r["row_id"] == ROW)
        selector = next(s for s in crossref_selectors([platform]) if s.row_id == ROW)
        records = read_csv(args.processed_root / f"records_{ROW}.csv")
        works = {w["canonical_work_id"]: w for w in read_csv(
            args.processed_root / "works_included.csv") if w["row_id"] == ROW}
        interim = read_csv(args.interim_root / f"crossref_works__{ROW}.csv")
        run_manifest = args.manifest_root / args.run / f"{args.run}.json"
        scope = json.loads(run_manifest.read_text(encoding="utf-8"))["scopes"][f"crossref/{SCOPE}"]
        selected = args.manifest_root / args.run / f"crossref__{SCOPE}__{scope['selected_walk_id']}.manifest.jsonl"
        paths = [("selected", selected)] + [
            (f"historical_{wid}", args.manifest_root / "run_20261026_01" /
             f"crossref__{SCOPE}__{wid}.manifest.jsonl") for wid in ("w01", "w02")]
        output = {"run_id": args.run,
                  "record_year_checks": {str(y): reconcile_year(records, works, y) for y in (2012, 2013)},
                  "interim_2012": population([r for r in interim if r["issued"][:4] == "2012"],
                                             platform["doi_version_pattern"]),
                  "raw_walk_checks": [], "errors": []}
        store = RawStore(args.raw_root)
        for label, path in paths:
            try:
                walk, raw = raw_records(path, store, selector)
                if label == "selected" and not walk.is_complete:
                    raise ValueError(f"selected walk is {walk.state}, not complete")
                output["raw_walk_checks"].append({
                    "label": label, "manifest": str(path), "walk_state": walk.state,
                    "walk_reason": walk.reason, "pages_checked": len(walk.pages),
                    **compare(raw, interim, records, platform["doi_version_pattern"])})
            except (OSError, ValueError, KeyError) as exc:
                output["errors"].append(f"{label}: {exc}")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2 if output["errors"] else 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(f"check_f1000_early_years: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
