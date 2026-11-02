"""D-041: Gates Open Research / VeriXiv pairs from Crossref relations, either side.

Synthetic records: three pairs (asserted by the preprint only, by both
sides, by the article only), one preprint and one article without any
relation (same title — titles never pair), one conflict.  Nothing here
touches OpenAlex.
"""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from src.common.config import load_sources_config
from src.common.interim import read_csv
from src.common.preprint_pairs import (SIDE_ARTICLE, SIDE_BOTH, SIDE_PREPRINT,
                                       build_pair_index, pair_specs)
from src.common.register import load_platforms
from tests.offline import FixtureTransport, run_full_pipeline



def _work(doi, kind, year, month, relation=None, title="Synthetic record"):
    item = {"DOI": doi, "type": kind, "prefix": "10.12688", "member": "0", "title": [title],
            "container-title": ["Gates Open Research"] if kind == "journal-article" else ["VeriXiv"],
            "created": {"date-time": f"{year}-{month:02d}-02T10:00:00Z"},
            "deposited": {"date-time": f"{year}-{month:02d}-02T10:00:00Z"},
            "indexed": {"date-time": f"{year}-{month:02d}-03T00:00:00Z"},
            "issued": {"date-parts": [[year, month, 1]]}}
    if kind == "posted-content":
        item["subtype"] = "preprint"
        item["posted"] = {"date-parts": [[year, month, 1]]}
    if relation:
        item["relation"] = relation
    return item


def _review(doi, target, year, month):
    return {"DOI": doi, "type": "peer-review", "prefix": "10.21956", "member": "0", "title": ["Synthetic record"],
            "container-title": [], "created": {"date-time": f"{year}-{month:02d}-02T10:00:00Z"},
            "deposited": {"date-time": f"{year}-{month:02d}-02T10:00:00Z"},
            "indexed": {"date-time": f"{year}-{month:02d}-03T00:00:00Z"},
            "relation": {"is-review-of": [{"id": target, "id-type": "doi"}]},
            "issued": {"date-parts": [[year, month, 1]]}}


def _rel(kind, doi):
    return {kind: [{"id": doi, "id-type": "doi", "asserted-by": "subject"}]}


# preprint-only pair (3010), both-sides pair (3011), article-only pair (3012);
# 3003 / 44 carry no relation and share a title.
ARTICLES = [
    _work("10.12688/gatesopenres.3010.1", "journal-article", 2024, 9),
    _work("10.12688/gatesopenres.3011.1", "journal-article", 2024, 10, _rel("has-preprint", "10.12688/verixiv.51.1")),
    _work("10.12688/gatesopenres.3012.1", "journal-article", 2024, 11, _rel("has-preprint", "10.12688/verixiv.52.1")),
    _work("10.12688/gatesopenres.3012.2", "journal-article", 2025, 1, _rel("has-preprint", "10.12688/verixiv.52.1")),   # not version 1
]
PREPRINTS = [
    _work("10.12688/verixiv.50.1", "posted-content", 2024, 3, _rel("is-preprint-of", "10.12688/gatesopenres.3010.1")),
    _work("10.12688/verixiv.51.1", "posted-content", 2024, 4, _rel("is-preprint-of", "10.12688/gatesopenres.3011.1")),
    _work("10.12688/verixiv.52.1", "posted-content", 2024, 5),
]
REVIEWS = [
    _review("10.21956/gatesopenres.3010.r1", "10.12688/gatesopenres.3010.1", 2024, 10),
    _review("10.21956/gatesopenres.3011.r1", "10.12688/gatesopenres.3011.1", 2024, 11),
    _review("10.21956/gatesopenres.3012.r1", "10.12688/gatesopenres.3012.1", 2024, 12),
    _review("10.21956/verixiv.50.r1", "10.12688/verixiv.50.1", 2024, 4),
    _review("10.21956/verixiv.51.r1", "10.12688/verixiv.51.1", 2024, 5),
    _review("10.21956/verixiv.52.r1", "10.12688/verixiv.52.1", 2024, 6),
]


class PairTransport(FixtureTransport):
    """The shared Crossref fixtures plus the D-041 records for prefix 10.12688 / 10.21956."""

    EXTRA = {("10.12688", "journal-article"): ARTICLES, ("10.12688", "posted-content"): PREPRINTS,
             ("10.21956", "peer-review"): REVIEWS}

    def __call__(self, url, headers, timeout):
        parts = urlsplit(url)
        if parts.netloc != "api.crossref.org":
            return super().__call__(url, headers, timeout)
        self.requests.append({"url": url, "headers": dict(headers)})
        query = parse_qs(parts.query)
        filters = dict(item.split(":", 1) for item in query.get("filter", [""])[0].split(",") if ":" in item)
        key = (filters.get("prefix", ""), filters.get("type", ""))
        base = json.loads(FixtureTransport._crossref(query))["message"]
        if key not in self.EXTRA:
            return 200, {}, json.dumps({"status": "ok", "message": base}).encode()
        # Re-paginate the fixture items plus the extra records.
        fixture_dir = Path(__file__).parent / "fixtures" / "crossref"
        items = [it for p in sorted(fixture_dir.glob(f"works__{key[0]}__{key[1]}__page*.json"))
                 for it in json.loads(p.read_bytes())["message"]["items"]] + self.EXTRA[key]
        cursor = unquote(query.get("cursor", ["*"])[0])
        match = re.match(r"CURSOR-\w+-(\d+)$", cursor)
        page = int(match.group(1)) if match else 1
        rows = int(query.get("rows", ["1000"])[0])
        part = items[(page - 1) * rows:page * rows]
        payload = {"status": "ok", "message": {"items": part, "total-results": len(items),
                                                "next-cursor": f"CURSOR-PAIR-{page + 1}" if part else None}}
        return 200, {}, json.dumps(payload).encode()


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    return run_full_pipeline(tmp_path_factory.mktemp("d041"), transport=PairTransport(), with_figures=False)


def test_register_declares_the_pair():
    specs = pair_specs(load_platforms())
    assert [(s.preprint_row, s.article_row) for s in specs] == [("verixiv", "gates_open_research")]
    spec = specs[0]
    assert spec.relation_from_preprint == "is-preprint-of" and spec.relation_from_article == "has-preprint"
    assert spec.is_article_version("10.12688/gatesopenres.3012.1") and not spec.is_article_version("10.12688/gatesopenres.3012.2")


def test_pairs_resolved_from_either_side_with_sides_recorded(outputs):
    records = read_csv(outputs.processed / "records_verixiv.csv")
    works = {r["source_record_id"]: r for r in records if r["row_entity_type"] == "work_record"}
    assert works["10.12688/verixiv.50.1"]["canonical_work_id"] == "doi:10.12688/gatesopenres.3010"
    assert works["10.12688/verixiv.50.1"]["correspondence_basis"] == SIDE_PREPRINT
    assert works["10.12688/verixiv.51.1"]["canonical_work_id"] == "doi:10.12688/gatesopenres.3011"
    assert works["10.12688/verixiv.51.1"]["correspondence_basis"] == SIDE_BOTH
    assert works["10.12688/verixiv.52.1"]["canonical_work_id"] == "doi:10.12688/gatesopenres.3012"
    assert works["10.12688/verixiv.52.1"]["correspondence_basis"] == SIDE_ARTICLE
    assert works["10.12688/verixiv.44.1"]["canonical_work_id"] == "doi:10.12688/verixiv.44"     # no relation, same title: no pair
    assert works["10.12688/verixiv.44.1"]["correspondence_basis"] == ""
    # review relations follow the paired identifier, so the preprint keeps its qualifying review
    relations = [r for r in records if r["row_entity_type"] == "evaluation_relation"]
    assert {r["reviewed_canonical_work_id"] for r in relations if r["review_record_id"] == "10.21956/verixiv.50.r1"} \
        == {"doi:10.12688/gatesopenres.3010"}
    gates = {r["source_record_id"]: r for r in read_csv(outputs.processed / "records_gates_open_research.csv")
             if r["row_entity_type"] == "work_record"}
    assert gates["10.12688/gatesopenres.3010.1"]["correspondence_basis"] == SIDE_PREPRINT
    assert gates["10.12688/gatesopenres.3011.1"]["correspondence_basis"] == SIDE_BOTH
    assert gates["10.12688/gatesopenres.3012.1"]["correspondence_basis"] == SIDE_ARTICLE
    assert gates["10.12688/gatesopenres.3003.1"]["correspondence_basis"] == ""
    assert gates["10.12688/gatesopenres.3010.1"]["canonical_work_id"] == "doi:10.12688/gatesopenres.3010"  # the article keeps its identifier


def test_row_series_unchanged_and_each_pair_counted_once(outputs):
    included = [r for r in read_csv(outputs.processed / "works_included.csv") if r["included"] == "true"]
    by_row = {}
    for r in included:
        by_row.setdefault(r["row_id"], []).append(r)
    assert len(by_row["verixiv"]) == 3 and len(by_row["gates_open_research"]) == 4
    assert all(r["counting_year"] == "2024" for r in by_row["verixiv"] + by_row["gates_open_research"])
    # row series: each row keeps its own count
    cells = {(c["row_id"], c["year"]): c for c in read_csv(outputs.tables / "works_by_row_year.csv")}
    assert cells[("verixiv", "2024")]["count"] == "3"
    assert cells[("gates_open_research", "2024")]["count"] == "4"
    # one line per pair in the overlap table, attributed to the earliest counting event
    overlap = {r["canonical_work_id"]: r for r in read_csv(outputs.tables / "cross_platform_overlap.csv")
               if "verixiv" in r["row_ids"]}
    assert set(overlap) == {f"doi:10.12688/gatesopenres.{s}" for s in ("3010", "3011", "3012")}
    for row in overlap.values():
        assert row["row_ids"] == "gates_open_research; verixiv"
        assert row["earliest_row_id"] == "verixiv" and row["earliest_year"] == "2024"
    assert overlap["doi:10.12688/gatesopenres.3010"]["correspondence_basis"] == SIDE_PREPRINT
    assert overlap["doi:10.12688/gatesopenres.3011"]["correspondence_basis"] == SIDE_BOTH
    assert overlap["doi:10.12688/gatesopenres.3012"]["correspondence_basis"] == SIDE_ARTICLE
    # deduplicated: each paired work counts once. While VeriXiv is provisional it is outside
    # the deduplicated tables (headline rows), so the pairs sit with the article row.
    unique = {(c["row_id"], c["year"]): c for c in read_csv(outputs.tables / "unique_works_all_rows_by_row_year.csv")}
    assert ("verixiv", "2024") not in unique
    assert unique[("gates_open_research", "2024")]["count"] == "4"
    assert [c for c in read_csv(outputs.tables / "unique_works_all_rows_year.csv") if c["year"] == "2024"][0]["count"] \
        in ("", "4")   # blank when another headline row blocks the all-rows cell; never 7


def test_pairs_follow_the_earliest_counting_event_once_verixiv_is_not_provisional(outputs, tmp_path):
    from copy import deepcopy
    from src.analyse import build_aggregates
    from src.common.log import JsonlLogger
    platforms = deepcopy(outputs.platforms)
    next(r for r in platforms if r["row_id"] == "verixiv")["provisional"] = False
    logger = JsonlLogger(outputs.run_config.run_id, log_dir=tmp_path / "logs")
    build_aggregates.run(outputs.run_config, load_sources_config(), platforms, logger, processed_root=outputs.processed,
                         manifest_root=outputs.roots["manifest_root"], tables_root=tmp_path / "tables")
    unique = {(c["row_id"], c["year"]): c for c in read_csv(tmp_path / "tables" / "unique_works_all_rows_by_row_year.csv")}
    assert unique[("verixiv", "2024")]["count"] == "3"                  # the three pairs: preprint posted first
    assert unique[("gates_open_research", "2024")]["count"] == "1"      # 3003 only
    cells = {(c["row_id"], c["year"]): c for c in read_csv(tmp_path / "tables" / "works_by_row_year.csv")}
    assert cells[("gates_open_research", "2024")]["count"] == "4"       # row series unchanged

def test_normalisation_summary_reports_pairs(outputs):
    summary = json.loads((outputs.processed / "normalisation_summary.json").read_text(encoding="utf-8"))
    (pairs,) = summary["preprint_pairs"]
    assert pairs["preprint_row"] == "verixiv" and pairs["article_row"] == "gates_open_research"
    assert pairs["n_pairs"] == 3 and pairs["n_conflicts"] == 0
    assert pairs["by_basis"] == {SIDE_PREPRINT: 1, SIDE_ARTICLE: 1, SIDE_BOTH: 1}


def _spec():
    return pair_specs(load_platforms())[0]


def test_conflicting_relations_leave_both_unpaired():
    spec = _spec()
    index = build_pair_index(spec, [
        {"doi": "10.12688/verixiv.60.1", "type": "posted-content",
         "relation_json": json.dumps({"is-preprint-of": [{"id": "10.12688/gatesopenres.3020.1", "id-type": "doi"},
                                                         {"id": "10.12688/gatesopenres.3021.1", "id-type": "doi"}]})},
        {"doi": "10.12688/verixiv.61.1", "type": "posted-content",
         "relation_json": json.dumps(_rel("is-preprint-of", "10.12688/gatesopenres.3022.1"))},
    ], [])
    assert index.lookup("verixiv", "10.12688/verixiv.60") is None
    assert index.lookup("verixiv", "10.12688/verixiv.61") == ("10.12688/gatesopenres.3022", SIDE_PREPRINT)
    assert index.lookup("gates_open_research", "10.12688/gatesopenres.3022") == ("10.12688/gatesopenres.3022", SIDE_PREPRINT)
    assert len(index.conflicts) == 2 and index.summary()["n_pairs"] == 1


def test_foreign_targets_and_other_types_are_ignored():
    spec = _spec()
    index = build_pair_index(spec, [
        {"doi": "10.12688/verixiv.70.1", "type": "posted-content",
         "relation_json": json.dumps(_rel("is-preprint-of", "10.1101/2024.01.01.000001"))},   # not a Gates DOI
        {"doi": "10.12688/verixiv.71.1", "type": "posted-content", "relation_json": ""},
    ], [
        {"doi": "10.12688/gatesopenres.3030.2", "type": "journal-article",
         "relation_json": json.dumps(_rel("has-preprint", "10.12688/verixiv.72.1"))},                    # version 2, not 1
        {"doi": "10.12688/gatesopenres.3031.1", "type": "peer-review",
         "relation_json": json.dumps(_rel("has-preprint", "10.12688/verixiv.73.1"))},                    # not a work type
    ])
    assert index.pairs == [] and index.conflicts == []
