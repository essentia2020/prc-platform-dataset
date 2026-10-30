"""Totals are sums of published yearly cells; no hidden grand total (§6, §9)."""

import csv


def test_row_total_equals_sum_of_year_cells(pipeline_outputs):
    out = pipeline_outputs
    for summary in out.table("register_summary"):
        row_id = summary["row_id"]
        cells = out.cells("works_by_row_year", row_id=row_id)
        if summary["unique_works_to_cutoff"] == "":
            continue
        yearly = sum(int(c["count"]) for c in cells if c["count"] != "")
        included = [w for w in out.works(row_id) if w["included"] == "true"]
        assert yearly == int(summary["unique_works_to_cutoff"]) == len({w["canonical_work_id"] for w in included})


def test_group_tables_have_no_grand_total_row(pipeline_outputs):
    out = pipeline_outputs
    classes = {str(p["initiation_class"]) for p in out.platforms}
    for r in out.table("works_by_class_year"):
        assert r["initiation_class"] in classes
        assert r["additivity"] == "row_summed"
    configs = {str(p["prc_configuration"]) for p in out.platforms}
    for r in out.table("works_by_configuration_year"):
        assert r["prc_configuration"] in configs
    for r in out.table("unique_works_all_rows_year"):
        assert r["additivity"] == "deduplicated"


def _blocking(member):
    """D-038 (amended): statuses that blank a group cell; not_applicable / observed_zero never do."""
    if member["observation_status"] in ("not_applicable", "register_only"):
        return None
    if member["source_observability_status"] in ("unknown_scope", "pending_run", "selector_no_match",
                                                 "source_not_covering"):
        return member["source_observability_status"]
    if member["coverage"] == "partial_coverage":
        return "partial_coverage"
    if member["count"] == "":
        return member["extraction_status"]
    return None


def test_row_summed_equals_sum_of_row_cells_and_dedup_is_not_larger(pipeline_outputs):
    out = pipeline_outputs
    by_class = {}
    for p in out.platforms:
        if p["register_status"] == "quantified" and not p.get("provisional"):
            by_class.setdefault(str(p["initiation_class"]), []).append(str(p["row_id"]))
    seen_blank = seen_sum = False
    for cls, row_ids in by_class.items():
        for summed in out.cells("works_by_class_year", initiation_class=cls):
            year = summed["year"]
            members = {r: out.cell("works_by_row_year", row_id=r, year=year) for r in row_ids}
            blocking = sorted(f"{r}:{_blocking(m)}" for r, m in members.items() if _blocking(m))
            if blocking:
                assert summed["count"] == "" and summed["observation_status"] == "not_observable"
                assert summed["blocking_rows"] == "; ".join(blocking)
                seen_blank = True
                continue
            contributing = [m for m in members.values() if m["observation_status"] not in ("not_applicable", "register_only")]
            assert int(summed["count"]) == sum(int(m["count"]) for m in contributing)
            assert summed["blocking_rows"] == ""
            dedup = out.cell("unique_works_by_class_year", initiation_class=cls, year=year)
            assert int(dedup["count"]) <= int(summed["count"])
            seen_sum = True
    assert seen_blank and seen_sum


def test_not_applicable_members_do_not_blank_a_group(pipeline_outputs):
    """Rows outside their eligible range never block the sum (D-038 as amended)."""
    out = pipeline_outputs
    # mixed class in 2021: jmirx_med is in range, the other mixed rows are not yet (not_applicable)
    members = {p["row_id"]: out.cell("works_by_row_year", row_id=p["row_id"], year=2021)
               for p in out.platforms if p["initiation_class"] == "mixed" and p["register_status"] == "quantified"}
    statuses = {m["observation_status"] for m in members.values()}
    assert "not_applicable" in statuses and "observed_zero" in statuses
    cell = out.cell("works_by_class_year", initiation_class="mixed", year=2021)
    assert cell["count"] == "0" and cell["observation_status"] == "observed_zero" and cell["blocking_rows"] == ""


def test_partial_coverage_member_blanks_group_and_footnote_names_it(pipeline_outputs):
    out = pipeline_outputs
    # community_initiated 2024: prereview / prelights carry data_status partial_coverage
    cell = out.cell("works_by_class_year", initiation_class="community_initiated", year=2024)
    assert cell["count"] == "" and "prereview:partial_coverage" in cell["blocking_rows"]
    md = (out.tables / "works_by_class_year.md").read_text(encoding="utf-8")
    assert "Blank group cells (D-038)" in md and "- community_initiated, 2024: " in md
    assert "prereview:partial_coverage" in md


def test_blank_group_statuses_are_from_the_closed_vocabulary(pipeline_outputs):
    out = pipeline_outputs
    allowed = {"unknown_scope", "pending_run", "selector_no_match", "source_not_covering", "partial_coverage",
               "incomplete", "failed"}
    for name in ("works_by_class_year", "works_by_configuration_year", "unique_works_by_class_year",
                 "unique_works_by_configuration_year", "unique_works_all_rows_year"):
        for r in out.table(name):
            entries = [e for e in r["blocking_rows"].split("; ") if e]
            assert (r["count"] == "") == bool(entries), (name, r)
            for e in entries:
                row_id, status = e.split(":")
                assert status in allowed and row_id


def test_overlap_is_reported_and_qeios_pair_disjoint(pipeline_outputs):
    out = pipeline_outputs
    overlap = out.table("cross_platform_overlap")
    shared = {r["canonical_work_id"]: r for r in overlap}
    assert "doi:10.1101/2024.01.01.000001" in shared
    assert set(shared["doi:10.1101/2024.01.01.000001"]["row_ids"].split("; ")) == {"prereview", "qeios_external_works"}
    assert shared["doi:10.1101/2024.01.01.000001"]["earliest_row_id"] == "prereview"
    for r in overlap:
        assert not {"qeios_hosted_works", "qeios_external_works"} <= set(r["row_ids"].split("; "))
    # the overlapping work is still counted in both rows (reported, not removed)
    assert out.cell("works_by_row_year", row_id="prereview", year=2024)["count"] == "1"
    assert out.cell("works_by_row_year", row_id="qeios_external_works", year=2024)["count"] == "2"
    # the all-rows cell for 2024 is blank in the fixture run (partial_coverage members) and says why
    all_2024 = out.cell("unique_works_all_rows_year", year=2024)
    assert all_2024["count"] == "" and "partial_coverage" in all_2024["blocking_rows"]


def test_markdown_tables_mirror_csv(pipeline_outputs):
    out = pipeline_outputs
    for csv_path in sorted(out.tables.glob("*.csv")):
        md = (out.tables / (csv_path.stem + ".md")).read_text(encoding="utf-8")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            n_rows = sum(1 for _ in csv.DictReader(handle))
        assert md.count("\n| ") - 1 == n_rows, csv_path.name      # header line + data lines
        assert "Analysis cutoff: 2026-09-30" in md and "year_to_date" in md and "Additivity" in md
