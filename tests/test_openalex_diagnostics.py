"""D-066: OpenAlex diagnostics — offline, on a synthetic works_included.csv.

No request leaves the test: an in-memory transport answers api.openalex.org
from a small table of works.  Checks: rows written only to the
data-quality log, key never persisted, residual-only pair signal, request
cap, walk reuse without requests, rows of other origins untouched.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from src.analyse.build_aggregates import DQ_COLUMNS
from src.common.config import load_sources_config
from src.common.interim import read_csv, write_csv
from src.common.manifest import list_walks, load_run_manifest, run_manifest_path, write_run_manifest
from src.common.register import load_platforms
from src.extract import openalex_diagnostics as oa
from tests.offline import JsonlLogger, make_run_config

KEY = "test-key-0123456789abcdef-SECRET"
GATES, VERIXIV, F1000 = "gates_open_research", "verixiv", "f1000research"

# doi -> (openalex work id, publication_year, source id)
OPENALEX = {
    "10.12688/gatesopenres.3003.1": ("W1", 2024, "S1"),
    "10.12688/gatesopenres.3010.1": ("W2", 2024, "S1"),     # residual pair with verixiv.50 (OpenAlex only)
    "10.12688/verixiv.50.1": ("W2", 2024, "S2"),
    "10.12688/verixiv.44.1": ("W3", 2025, "S2"),
    "10.12688/f1000research.100.1": ("W4", 2023, "S3"),
    # f1000research.101.1 is absent from OpenAlex; verixiv.51/gates 3011 are a Crossref pair (D-041)
    "10.12688/verixiv.51.1": ("W5", 2024, "S2"),
    "10.12688/gatesopenres.3011.1": ("W5", 2024, "S1"),
    "10.12688/f1000research.103.1": ("W6", 2023, "S3", "10.12688/f1000research.900.1"),  # served under another DOI
}
SOURCE_YEARS = {"S3": {"2022": 500, "2023": 620}}


WORK_COLUMNS = ["row_id", "canonical_work_id", "work_doi", "counting_record_id", "posting_record_id",
                "included", "counting_year", "correspondence_basis"]


def _included(row_id, doi, year, basis=""):
    stem = doi.rsplit(".", 1)[0]
    row = {c: "" for c in WORK_COLUMNS}
    row.update({
        "row_id": row_id,
        "canonical_work_id": f"doi:{stem}",
        "work_doi": stem,
        "counting_record_id": doi,
        "posting_record_id": doi,
        "included": "true",
        "counting_year": str(year),
        "correspondence_basis": basis,
    })
    return row


WORKS = [
    _included(GATES, "10.12688/gatesopenres.3003.1", 2024),
    _included(GATES, "10.12688/gatesopenres.3010.1", 2024),
    _included(GATES, "10.12688/gatesopenres.3011.1", 2024, "is_preprint_of+has_preprint"),
    _included(VERIXIV, "10.12688/verixiv.50.1", 2024),
    _included(VERIXIV, "10.12688/verixiv.44.1", 2025),
    _included(VERIXIV, "10.12688/verixiv.51.1", 2024, "is_preprint_of+has_preprint"),
    _included(F1000, "10.12688/f1000research.100.1", 2023),
    _included(F1000, "10.12688/f1000research.101.1", 2023),
    _included(F1000, "10.12688/f1000research.103.1", 2023),
    {**{c: "" for c in WORK_COLUMNS}, "row_id": F1000, "canonical_work_id": "doi:10.12688/f1000research.102",
     "work_doi": "10.12688/f1000research.102", "counting_record_id": "10.12688/f1000research.102.1",
     "included": "false"},
]


class OpenAlexTransport:
    def __init__(self, fail_for=None, require_header=True):
        self.requests = []
        self.fail_for = fail_for or ()
        self.require_header = require_header

    def __call__(self, url, headers, timeout):
        self.requests.append({"url": url, "headers": dict(headers)})
        parts = urlsplit(url)
        assert parts.netloc == "api.openalex.org"
        assert "api_key" not in parse_qs(parts.query)
        if self.require_header and headers.get("Authorization") != f"Bearer {KEY}":
            return 401, {}, b'{"error": "missing key"}'
        query = parse_qs(parts.query)
        filters = dict(item.split(":", 1) for item in unquote(query["filter"][0]).split(",") if ":" in item)
        if any(marker in url for marker in self.fail_for):
            return 500, {}, b"boom"
        if "group_by" in query:
            source = filters["primary_location.source.id"]
            groups = [{"key": y, "key_display_name": y, "count": n} for y, n in SOURCE_YEARS.get(source, {}).items()]
            return 200, {}, json.dumps({"meta": {"count": sum(g["count"] for g in groups)}, "group_by": groups}).encode()
        dois = filters["doi"].split("|")
        assert len(dois) <= 100
        results = []
        for doi in dois:
            hit = OPENALEX.get(doi)
            if hit:
                wid, year, source, *served = hit
                served_doi = served[0] if served else doi
                results.append({"id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{served_doi}",
                                "publication_year": year,
                                "primary_location": {"source": {"id": f"https://openalex.org/{source}"}}})
        return 200, {}, json.dumps({"meta": {"count": len(results)}, "results": results}).encode()


def _setup(tmp_path, per_request_cap=100, max_requests=4000, source_ids=None):
    run_config = make_run_config("2026-09-30")
    sources = load_sources_config()
    block = sources["sources"]["openalex"]
    block["per_request_cap"] = per_request_cap
    block["budget"]["max_requests_per_run"] = max_requests
    block["source_ids"] = source_ids or {}
    processed = tmp_path / "processed"
    processed.mkdir()
    write_csv(processed / "works_included.csv", WORK_COLUMNS, WORKS)
    preset = {c: "" for c in DQ_COLUMNS}
    preset.update(issue_id="DQ-001", row_id=GATES, issue_type="other", description="preset row", status="template",
                  origin="preset", n_records_affected="0")
    analyse_row = {c: "" for c in DQ_COLUMNS}
    analyse_row.update(issue_id=f"DQ-{run_config.run_id}-001", row_id=F1000, issue_type="withdrawn_record",
                       description="analyse row", status="observed", origin="run", run_id=run_config.run_id,
                       walk_id="w01", n_records_affected="1")
    write_csv(processed / "data_quality_log.csv", DQ_COLUMNS, [preset, analyse_row])
    manifests = tmp_path / "manifests"
    write_run_manifest(run_manifest_path(manifests, run_config.run_id),
                       {"run_id": run_config.run_id, "scopes": {}})
    logger = JsonlLogger(run_config.run_id, log_dir=tmp_path / "logs")
    roots = dict(processed_root=processed, manifest_root=manifests, raw_root=tmp_path / "raw")
    return run_config, sources, logger, roots


def _run(tmp_path, transport=None, **kw):
    run_config, sources, logger, roots = _setup(tmp_path, **{k: v for k, v in kw.items()
                                                             if k in ("per_request_cap", "max_requests", "source_ids")})
    transport = transport or OpenAlexTransport()
    result = oa.run(run_config, sources, load_platforms(), logger, transport=transport, sleeper=lambda _: None,
                    api_key=KEY, **roots)
    return run_config, roots, transport, result


def _all_text(root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*") if p.is_file())


def test_volume_check_rows_per_quantified_crossref_row(tmp_path):
    run_config, roots, transport, result = _run(tmp_path, source_ids={F1000: "S3"})
    rows = {(r["row_id"], r["issue_type"]): r for r in result["rows"]}
    assert set(rows) == {(GATES, "openalex_volume_check"), (VERIXIV, "openalex_volume_check"),
                         (F1000, "openalex_volume_check"), (GATES, "openalex_pair_signal")}
    f1000 = rows[(F1000, "openalex_volume_check")]
    assert f1000["n_records_affected"] == "2"  # 101.1 absent, 103.1 served under another DOI
    assert "2023: row=3 found=1 year_agree=1 source=620" in f1000["description"]
    assert f1000["status"] == "observed" and f1000["origin"] == "run" and f1000["run_id"] == run_config.run_id
    assert f1000["effect_on_counts"] == "none (diagnostic)"
    assert f1000["issue_id"].startswith(f"DQ-{run_config.run_id}-oa-")
    assert "source_years__f1000research=" in f1000["walk_id"]
    verixiv = rows[(VERIXIV, "openalex_volume_check")]
    assert verixiv["n_records_affected"] == "0"
    assert "2025: row=1 found=1 year_agree=1" in verixiv["description"] and "source=" not in verixiv["description"]
    # the excluded work (102.1) is never sent
    assert not any("f1000research.102" in r["url"] for r in transport.requests)


def test_volume_check_resolves_counting_record_doi_not_stem(tmp_path):
    # work_doi is the version-stripped stem; OpenAlex only knows the record DOI.
    run_config, roots, transport, result = _run(tmp_path)
    rows = {(r["row_id"], r["issue_type"]): r for r in result["rows"]}
    gates = rows[(GATES, "openalex_volume_check")]
    assert gates["n_records_affected"] == "0"
    assert "found=0" not in gates["description"]
    assert all("gatesopenres.3003.1" in r["url"] or "gatesopenres" not in r["url"] for r in transport.requests)
    assert not any(r["url"].rstrip("&").endswith("gatesopenres.3003") for r in transport.requests)


def test_pair_signal_runs_on_the_residual_only(tmp_path):
    _, _, _, result = _run(tmp_path)
    (pair,) = [r for r in result["rows"] if r["issue_type"] == "openalex_pair_signal"]
    assert pair["row_id"] == GATES and pair["n_records_affected"] == "1"
    assert "2 residual verixiv works and 2 residual gates_open_research works" in pair["description"]
    assert "10.12688/verixiv.50.1=10.12688/gatesopenres.3010.1" in pair["description"]
    assert "verixiv.51" not in pair["description"]                  # Crossref-paired works are not re-tested
    assert "cross_platform_overlap.csv" in pair["handling"]


def test_rows_go_to_the_log_only_and_other_rows_survive(tmp_path):
    run_config, roots, _, result = _run(tmp_path)
    log = read_csv(roots["processed_root"] / "data_quality_log.csv")
    assert [r["issue_id"] for r in log[:2]] == ["DQ-001", f"DQ-{run_config.run_id}-001"]
    assert len(log) == 2 + len(result["rows"])
    assert list(log[0].keys()) == DQ_COLUMNS
    # minimal quoting as the analysis stage writes it
    raw = (roots["processed_root"] / "data_quality_log.csv").read_text(encoding="utf-8")
    assert not raw.startswith('"issue_id"')
    # works_included.csv is untouched
    assert read_csv(roots["processed_root"] / "works_included.csv") == [{k: w[k] for k in WORK_COLUMNS} for w in WORKS]
    # a second run replaces only its own rows
    oa.run(run_config, load_sources_config(), load_platforms(), JsonlLogger(run_config.run_id, log_dir=tmp_path / "l2"),
           transport=OpenAlexTransport(), sleeper=lambda _: None, api_key=KEY, **roots)
    again = read_csv(roots["processed_root"] / "data_quality_log.csv")
    assert len(again) == len(log) and [r["issue_id"] for r in again] == [r["issue_id"] for r in log]


def test_api_key_never_persisted(tmp_path):
    _, roots, transport, result = _run(tmp_path)
    assert all(r["headers"].get("Authorization") == f"Bearer {KEY}" for r in transport.requests)
    for root in (roots["raw_root"], roots["manifest_root"], tmp_path / "logs", roots["processed_root"]):
        assert KEY not in _all_text(root), root
    sidecars = list((roots["raw_root"] / "openalex").rglob("*.request.json"))
    assert sidecars
    record = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert record["headers"]["Authorization"] == "<redacted>"
    assert "api_key" not in record["parameters"]


def test_key_from_environment_only(tmp_path, monkeypatch):
    run_config, sources, logger, roots = _setup(tmp_path)
    monkeypatch.delenv("PRC_OPENALEX_API_KEY", raising=False)
    with pytest.raises(oa.OpenAlexConfigError):
        oa.run(run_config, sources, load_platforms(), logger, transport=OpenAlexTransport(), **roots)
    monkeypatch.setenv("PRC_OPENALEX_API_KEY", KEY)
    result = oa.run(run_config, sources, load_platforms(), logger, transport=OpenAlexTransport(),
                    sleeper=lambda _: None, **roots)
    assert result["rows"]


def test_batches_respect_the_per_request_cap(tmp_path):
    _, roots, transport, result = _run(tmp_path, per_request_cap=2)
    gates_requests = [r for r in transport.requests if "gatesopenres" in r["url"]]
    assert len(gates_requests) == 2                                  # three DOIs, two per request
    walks = list_walks(roots["manifest_root"], "run_test_01", "openalex", f"works_by_doi__{GATES}")
    assert len(walks) == 1 and walks[0].is_complete and len(walks[0].pages) == 2
    assert walks[0].completion["rule"] == oa.RULE_BATCHES and walks[0].completion["dois_requested"] == 3


def test_request_cap_closes_remaining_walks_without_rows(tmp_path):
    run_config, roots, transport, result = _run(tmp_path, max_requests=2)
    assert len(transport.requests) == 2
    rows = {(r["row_id"], r["issue_type"]) for r in result["rows"]}
    assert len(rows) <= 2
    record = load_run_manifest(run_manifest_path(roots["manifest_root"], run_config.run_id))["openalex_diagnostics"]
    assert record["requests_used"] == 2 and record["request_cap"] == 2
    assert any(s["state"] == "failed" and "request cap" in s["reason"] for s in record["scopes"].values())


def test_failed_scope_yields_no_row_and_does_not_stop_the_stage(tmp_path):
    _, roots, _, result = _run(tmp_path, transport=OpenAlexTransport(fail_for=("verixiv",)))
    types = {(r["row_id"], r["issue_type"]) for r in result["rows"]}
    assert (VERIXIV, "openalex_volume_check") not in types
    assert (GATES, "openalex_pair_signal") not in types               # one side unresolved: no signal
    assert (GATES, "openalex_volume_check") in types and (F1000, "openalex_volume_check") in types
    walks = list_walks(roots["manifest_root"], "run_test_01", "openalex", f"works_by_doi__{VERIXIV}")
    assert walks[0].state == "failed"


def test_complete_walks_are_reused_without_requests(tmp_path):
    run_config, roots, _, first = _run(tmp_path)

    def forbidden(*args):
        raise AssertionError("a complete walk must be reused without a request")

    second = oa.run(run_config, load_sources_config(), load_platforms(),
                    JsonlLogger(run_config.run_id, log_dir=tmp_path / "l2"), transport=forbidden, api_key=KEY, **roots)
    assert [r["description"] for r in second["rows"]] == [r["description"] for r in first["rows"]]
    assert second["record"]["requests_used"] == 0


def test_issue_types_are_in_the_dictionary_and_role_is_diagnostic():
    from tools import append_dq_rows
    assert set(oa.ISSUE_TYPES) <= append_dq_rows.issue_types()
    block = load_sources_config()["sources"]["openalex"]
    assert block["role"] == "diagnostic" and int(block["per_request_cap"]) <= 100
    assert block["auth"]["api_key_env"] == "PRC_OPENALEX_API_KEY"


def test_tracked_configuration_carries_no_key():
    for path in (Path("config/sources.yaml"), Path("config/run.yaml")):
        text = path.read_text(encoding="utf-8")
        assert "api_key:" not in text and "Bearer " not in text.replace("Bearer {key}", "")

def test_works_served_under_another_doi_are_counted_as_not_found_and_named(tmp_path):
    _, _, _, result = _run(tmp_path, source_ids={F1000: "S3"})
    rows = {(r["row_id"], r["issue_type"]): r for r in result["rows"]}
    f1000 = rows[(F1000, "openalex_volume_check")]
    assert f1000["n_records_affected"] == "2"
    assert "OpenAlex answered with 2 distinct works, 1 of them under a different primary DOI" in f1000["description"]
    assert "different primary DOI" not in rows[(GATES, "openalex_volume_check")]["description"]
