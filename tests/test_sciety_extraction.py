"""Offline run of the Sciety stage: docmap multiplicity (boundary test 8), account filtering, identities."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from src.common.interim import read_csv
from src.extract import sciety_evaluations
from src.extract.crossref_common import ExtractionIncomplete
from src.extract.selectors import sciety_scopes
from tests.offline import FixtureTransport, crossref_page, run_context
from src.normalise.sciety_integrity import PublisherAccountMismatch


def _run(tmp_path, transport=None):
    run_config, sources, platforms, logger, roots = run_context(tmp_path)
    transport = transport or FixtureTransport()
    outcomes = sciety_evaluations.run(run_config, sources, platforms, logger, transport=transport,
                                      sleeper=lambda s: None, **roots)
    return outcomes, roots, transport


def test_one_request_per_group_using_the_publisher_account_filter(tmp_path: Path):
    outcomes, _, transport = _run(tmp_path)
    assert all(o.complete for o in outcomes)
    urls = [r["url"] for r in transport.requests]
    assert len(urls) == len(outcomes)
    assert all("publisheraccount=https%3A%2F%2Fsciety.org%2Fgroups%2F" in u for u in urls)


def test_docmap_with_two_outputs_yields_two_evaluation_rows_for_one_work(tmp_path: Path):
    outcomes, roots, _ = _run(tmp_path)
    rows = read_csv(roots["interim_root"] / "sciety_evaluations__prereview.csv")
    first = [r for r in rows if r["evaluated_work_doi"] == "10.1101/2024.01.01.000001"]
    assert [r["evaluation_index"] for r in first] == ["0", "1"]
    assert first[0]["evaluation_id"].startswith("sciety:https://sciety.org/docmaps/v1/") and first[0]["evaluation_id"].endswith(":0")
    assert first[1]["evaluation_id"] == "10.5281/zenodo.0000001"   # DOI identity when the output carries one
    assert first[0]["evaluation_date"] == "2024-03-11" and first[1]["evaluation_date"] == "2024-03-12"
    assert {r["evaluation_type"] for r in first} == {"review-article"}
    # the work is a single evaluated work with two evaluation records
    assert len({r["evaluated_work_doi"] for r in first}) == 1


def test_docmap_publisher_mismatch_hard_fails_normalisation(tmp_path: Path):
    body = (Path(__file__).parent / "fixtures/sciety/index__prereview.json").read_bytes()
    transport = FixtureTransport(scripted={"groups%2Fprereview": [(200, {}, body)]})
    with pytest.raises(PublisherAccountMismatch):
        _run(tmp_path, transport)
    assert not (tmp_path / "interim/sciety_evaluations__prereview.csv").exists()


def test_evaluation_after_cutoff_is_kept_in_the_interim_layer(tmp_path: Path):
    _, roots, _ = _run(tmp_path)
    rows = read_csv(roots["interim_root"] / "sciety_evaluations__prereview.csv")
    late = next(r for r in rows if r["evaluated_work_doi"] == "10.1101/2024.02.02.000002")
    assert late["evaluation_date"] == "2026-10-03"   # the cutoff is applied in analysis, never in extraction


def test_empty_group_response_is_complete_with_zero_rows(tmp_path: Path):
    _, roots, _ = _run(tmp_path)
    rows = read_csv(roots["interim_root"] / "sciety_evaluations__metaror.csv")
    assert rows == []


def test_failed_group_blocks_only_that_row(tmp_path: Path):
    transport = FixtureTransport(scripted={"groups%2Fprereview": [crossref_page(503)] * 5})
    with pytest.raises(ExtractionIncomplete) as excinfo:
        _run(tmp_path, transport)
    assert "evaluations__prereview: failed (blocks prereview)" in str(excinfo.value)
    assert not (tmp_path / "interim" / "sciety_evaluations__prereview.csv").exists()
    assert (tmp_path / "interim" / "sciety_evaluations__metaror.csv").exists()


def test_scopes_cover_primary_and_cross_check_groups():
    from src.common.register import load_platforms
    scopes = sciety_scopes(load_platforms())
    by_row = {}
    for s in scopes:
        by_row.setdefault(s.row_id, []).append(s)
    assert by_row["elife_reviewed_preprints"][0].role == "cross_check"
    assert len(by_row["pci_recommendations"]) > 1
    assert by_row["prereview"][0].group_id == "10360d97-bf52-4aef-b2fa-2f60d319edd7"
    assert by_row["prereview"][0].account_matches("https://sciety.org/groups/prereview")
    assert by_row["prereview"][0].account_matches("https://sciety.org/groups/10360d97-bf52-4aef-b2fa-2f60d319edd7")
    assert not by_row["prereview"][0].account_matches("https://sciety.org/groups/elife")
