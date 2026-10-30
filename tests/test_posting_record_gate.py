"""D-060: posting-record gate, alternative selector signals, eligible-range summary.

Two first-public-posting rows counted the wrong population in run_20261027_01:

* eLife — journal-article records without a posted-content record of the same
  stem (pre-model articles) entered the row as postings;
* Access Microbiology — ``container_titles`` was conjunctive with ``doi_regex``,
  so posted-content records with an empty container-title never reached the
  interim file, while conference abstracts did.

The gate is read from ``eligibility_events`` (the event names the record type
``posted-content``), as D-036 reads the review requirement; nothing is keyed on
a row id.  ``register_summary`` and the deduplicated group series are
restricted to the eligible range.
"""

from __future__ import annotations

import json
from urllib.parse import unquote

import pytest

from tests.offline import FixtureTransport, _within_date_filters, run_full_pipeline
from src.analyse.build_aggregates import requires_posting_record
from src.common.register import load_platforms
from src.extract.selectors import CrossrefSelector, crossref_selectors as selectors_for

GATED_ROWS = {"elife_reviewed_preprints", "access_microbiology"}


def _item(doi: str, record_type: str, day: str, container: str | None) -> dict:
    y, m, d = (int(x) for x in day.split("-"))
    item = {"DOI": doi, "type": record_type, "prefix": doi.split("/")[0], "member": "0",
            "title": ["Synthetic record"], "container-title": [container] if container else [],
            "created": {"date-time": f"{day}T10:00:00Z"}, "deposited": {"date-time": f"{day}T10:00:00Z"},
            "indexed": {"date-time": f"{day}T12:00:00Z"}, "issued": {"date-parts": [[y, m, d]]}}
    if record_type == "posted-content":
        item["subtype"] = "preprint"
        item["posted"] = {"date-parts": [[y, m, d]]}
    else:
        item["published-online"] = {"date-parts": [[y, m, d]]}
    return item


ELIFE = {
    "posted-content": [
        _item("10.7554/elife.91984.1", "posted-content", "2023-03-14", "eLife"),
        _item("10.7554/elife.91984.2", "posted-content", "2023-08-01", "eLife"),   # revised Reviewed Preprint
        _item("10.7554/elife.80000.1", "posted-content", "2022-12-20", "eLife"),   # 2022 pilot posting
        _item("10.7554/elife.70000.1", "posted-content", "2021-10-01", "eLife"),   # before the eligible range
    ],
    "journal-article": [
        _item("10.7554/elife.91984", "journal-article", "2023-11-02", "eLife"),    # version of record of the RP
        _item("10.7554/elife.12345", "journal-article", "2015-06-01", "eLife"),    # pre-model article
        _item("10.7554/elife.80011", "journal-article", "2024-02-01", "eLife"),    # pre-model article in range
    ],
}
ACMI = {
    "posted-content": [
        _item("10.1099/acmi.0.000460.v1", "posted-content", "2022-05-10", None),   # empty container-title
        _item("10.1099/acmi.0.000900.v1", "posted-content", "2024-06-01", None),
    ],
    "journal-article": [
        _item("10.1099/acmi.0.000460.v3", "journal-article", "2023-01-15", "Access Microbiology"),
        _item("10.1099/acmi.0.000460", "journal-article", "2023-03-01", "Access Microbiology"),
        _item("10.1099/acmi.0.000100", "journal-article", "2019-08-01", "Access Microbiology"),  # pre-model article
        _item("10.1099/acmi.ac2019.po0077", "journal-article", "2019-04-01", "Access Microbiology"),  # abstract
        _item("10.1099/mic.0.001234", "journal-article", "2023-05-01", "Microbiology"),  # another journal
    ],
}


class PrefixItemsTransport(FixtureTransport):
    """Serve scripted Crossref items for chosen prefixes; everything else from the fixtures."""

    def __init__(self, items: dict[str, dict[str, list[dict]]]) -> None:
        super().__init__()
        self.items = items

    def _crossref(self, query):  # type: ignore[override]
        filters = dict(item.split(":", 1) for item in query.get("filter", [""])[0].split(",") if ":" in item)
        prefix, record_type = filters.get("prefix", ""), filters.get("type", "")
        if prefix not in self.items:
            return FixtureTransport._crossref(query)
        items = [i for i in self.items[prefix].get(record_type, []) if _within_date_filters(i, filters)]
        cursor = unquote(query.get("cursor", ["*"])[0])
        page = int(cursor.rsplit("-", 1)[1]) if cursor.startswith("CURSOR-") else 1
        rows = int(query.get("rows", ["1000"])[0])
        part = items[(page - 1) * rows:page * rows]
        return json.dumps({"status": "ok", "message": {"items": part, "total-results": len(items),
                           "next-cursor": f"CURSOR-D060-{page + 1}" if part else None}}).encode()


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    return run_full_pipeline(tmp_path_factory.mktemp("d060"),
                             transport=PrefixItemsTransport({"10.7554": ELIFE, "10.1099": ACMI}))


# ------------------------------------------------------------- register gate
def test_gate_is_read_from_eligibility_events_not_row_ids():
    rows = {r["row_id"]: r for r in load_platforms()}
    assert {rid for rid, r in rows.items() if requires_posting_record(r)} == GATED_ROWS
    f1000 = dict(rows["f1000research"])
    assert not requires_posting_record(f1000)                       # "(journal-article)" postings
    copernicus = rows["copernicus_interactive_public_peer_review"]
    assert not requires_posting_record(copernicus)                  # discussion papers deposited as journal-article
    detached = dict(rows["elife_reviewed_preprints"], row_id="other_row")
    assert requires_posting_record(detached)
    assert not requires_posting_record(dict(detached, counting_event="earliest_qualifying_evaluation"))
    assert not requires_posting_record(dict(detached, eligibility_events=["first public posting of version 1"]))


# ------------------------------------------------------------ selector signals
def _selector(row_id: str) -> CrossrefSelector:
    return next(s for s in selectors_for(load_platforms()) if s.row_id == row_id)


def test_access_microbiology_selector_admits_posted_content_without_container_title():
    sel = _selector("access_microbiology")
    assert sel.matches_work(ACMI["posted-content"][0])                 # empty container-title, regex matches
    assert sel.matches_work(ACMI["journal-article"][0])                # accepted version acmi.0.NNNNNN.v3
    assert sel.matches_work(ACMI["journal-article"][1])                # version of record acmi.0.NNNNNN
    assert not sel.matches_work(ACMI["journal-article"][3])            # conference abstract, journal title present
    assert not sel.matches_work(ACMI["journal-article"][4])            # another Microbiology Society journal
    assert not sel.container_titles


def test_doi_regex_and_container_titles_are_alternative_signals():
    row = dict(next(r for r in load_platforms() if r["row_id"] == "access_microbiology"))
    selector = json.loads(json.dumps(row["extraction_selector"]))
    selector["crossref"]["container_titles"] = ["Access Microbiology"]
    row["extraction_selector"] = selector
    sel = next(s for s in selectors_for([row]) if s.row_id == "access_microbiology")
    assert sel.matches_work(ACMI["posted-content"][0])                 # regex alone suffices
    assert sel.matches_work(ACMI["journal-article"][3])                # title alone suffices under the prefix
    assert not sel.matches_work(ACMI["journal-article"][4])            # neither signal
    # Title-only selectors (no doi_regex) keep the title as the discriminator under a wide prefix.
    jmirx = _selector("jmirx_med")
    assert jmirx.container_titles and not jmirx.doi_regex
    assert jmirx.matches_work(_item("10.2196/12345", "journal-article", "2022-01-01", "JMIRx Med"))
    assert not jmirx.matches_work(_item("10.2196/12345", "journal-article", "2022-01-01", "JMIR"))


# ---------------------------------------------------------------- pipeline
def _works(outputs, row_id: str) -> dict[str, dict]:
    return {w["canonical_work_id"]: w for w in outputs.works(row_id)}


def test_elife_counts_reviewed_preprints_only(outputs):
    works = _works(outputs, "elife_reviewed_preprints")
    assert set(works) == {"doi:10.7554/elife.91984", "doi:10.7554/elife.80000", "doi:10.7554/elife.70000",
                          "doi:10.7554/elife.12345", "doi:10.7554/elife.80011"}
    rp = works["doi:10.7554/elife.91984"]
    assert rp["included"] == "true" and rp["counting_year"] == "2023"
    assert rp["counting_record_id"] == "10.7554/elife.91984.1"       # the posting, not the version of record
    assert "10.7554/elife.91984" not in rp["contributing_record_ids"].split("; ")
    for old in ("doi:10.7554/elife.12345", "doi:10.7554/elife.80011"):
        assert works[old]["included"] == "false"
        assert works[old]["exclusion_reason"] == "no_posting_record"
        assert works[old]["counting_year"] == "" and works[old]["in_eligible_range"] == ""
    assert works["doi:10.7554/elife.80000"]["counting_year"] == "2022"
    assert outputs.cell("works_by_row_year", row_id="elife_reviewed_preprints", year=2022)["count"] == "1"
    assert outputs.cell("works_by_row_year", row_id="elife_reviewed_preprints", year=2023)["count"] == "1"
    assert outputs.cell("works_by_row_year", row_id="elife_reviewed_preprints", year=2024)["count"] == "0"
    diag = outputs.analysis_manifest["rows"]["elife_reviewed_preprints"]["diagnostics"]
    assert diag["excluded_no_posting_record"] == 2


def test_access_microbiology_start_is_the_first_posted_content_year(outputs):
    works = _works(outputs, "access_microbiology")
    assert "doi:10.1099/acmi.ac2019.po0077" not in works                # never flattened
    assert "doi:10.1099/mic.0.001234" not in works
    assert works["doi:10.1099/acmi.0.000100"]["exclusion_reason"] == "no_posting_record"
    first = works["doi:10.1099/acmi.0.000460"]
    assert first["included"] == "true" and first["counting_year"] == "2022"
    assert first["counting_record_id"] == "10.1099/acmi.0.000460.v1"
    summary = outputs.cell("register_summary", row_id="access_microbiology")
    assert summary["eligible_start_year"] == "2022"                    # not 2019 (pre-model article)
    assert summary["unique_works_to_cutoff"] == "2" and summary["n_works_excluded"] == "1"
    assert outputs.analysis_manifest["rows"]["access_microbiology"]["start_unresolved"] is False
    assert outputs.cell("works_by_row_year", row_id="access_microbiology", year=2021)["observation_status"] == \
        "not_applicable"


def test_register_summary_is_restricted_to_the_eligible_range(outputs):
    summary = outputs.cell("register_summary", row_id="elife_reviewed_preprints")
    assert summary["eligible_start_year"] == "2022"
    assert summary["first_year_with_data"] == "2022" and summary["last_year_with_data"] == "2023"
    assert summary["unique_works_to_cutoff"] == "2"                    # 80000 (2022) and 91984 (2023)
    assert summary["n_works_excluded"] == "2"                          # the two pre-model articles
    assert summary["n_works_outside_eligible_range"] == "1"            # 70000, posted 2021
    early = _works(outputs, "elife_reviewed_preprints")["doi:10.7554/elife.70000"]
    assert early["included"] == "true" and early["in_eligible_range"] == "false"
    assert outputs.cell("works_by_row_year", row_id="elife_reviewed_preprints", year=2021)["observation_status"] == \
        "not_applicable"


def test_every_work_file_reconciles_with_the_summary(outputs):
    for summary in outputs.table("register_summary"):
        if summary["unique_works_to_cutoff"] == "":
            continue
        works = outputs.works(summary["row_id"])
        counted = {w["canonical_work_id"] for w in works if w["in_eligible_range"] == "true"}
        included = {w["canonical_work_id"] for w in works if w["included"] == "true"}
        assert len(counted) == int(summary["unique_works_to_cutoff"])
        assert len(included) - len(counted) == int(summary["n_works_outside_eligible_range"])
        assert all(w["in_eligible_range"] == "" for w in works if w["included"] == "false")


# ------------------------------------------------------- dedup series (unit)
def _analysis(row: dict, start: int, works: list[tuple[str, int]]):
    from src.analyse.build_aggregates import RowAnalysis, WorkAnalysis
    from src.common.eligibility import WorkDecision
    from src.common.run_state import RowState
    state = RowState(row_id=row["row_id"], register_status="quantified",
                     primary_scopes={"crossref/works__x__posted-content": "complete"})
    a = RowAnalysis(row=row, state=state, effective_register_status="quantified")
    a.eligible_start, a.eligible_end = start, 2026
    for cwid, year in works:
        a.works.append(WorkAnalysis(row_id=row["row_id"], canonical_work_id=cwid, work_doi=cwid[4:],
                                    decision=WorkDecision(included=True, counting_event="first_public_posting",
                                                          counting_year=year, counting_record_id=cwid[4:]),
                                    posting=None, eligibility_review=None, counting_record=None,
                                    n_relations_flagged=0, attribution_basis=""))
    return a


def test_dedup_series_count_only_works_inside_each_rows_range():
    from datetime import date
    from src.analyse.build_aggregates import _dedup_cells, row_cells
    rows = {r["row_id"]: dict(r) for r in load_platforms()}
    elife = _analysis(rows["elife_reviewed_preprints"], 2022, [("doi:10.7554/elife.70000", 2021),
                                                                ("doi:10.7554/elife.80000", 2022)])
    f1000 = _analysis(rows["f1000research"], 2013, [("doi:10.12688/f1000research.1", 2021),
                                                    ("doi:10.12688/f1000research.2", 2022)])
    cutoff = date(2026, 9, 30)
    years = [2021, 2022]
    cells = {a.row_id: row_cells(a, years, cutoff) for a in (elife, f1000)}
    assert cells["elife_reviewed_preprints"][2021].observation_status == "not_applicable"
    assert elife.counted_works() == [elife.works[1]] and len(f1000.counted_works()) == 2
    table = {int(r["year"]): r for r in _dedup_cells([elife, f1000], cells, years, cutoff, None)}
    assert table[2021]["count"] == 1        # the 2021 eLife posting is outside its row's range
    assert table[2022]["count"] == 2
    assert table[2021]["n_author_initiated_by_earliest_event"] == 1
