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
        # included works counted outside the eligible range enter no cell and no total (D-060)
        counted = [w for w in out.works(row_id) if w["included"] == "true" and w["in_eligible_range"] == "true"]
        assert yearly == int(summary["unique_works_to_cutoff"]) == len({w["canonical_work_id"] for w in counted})


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


BLOCKING_SOURCE = ("unknown_scope", "pending_run", "selector_no_match")
LOWER_BOUND_COVERAGE = ("partial_coverage", "partial_known_scope")


def _classify(member):
    """D-061: which list of a group cell a member row cell belongs to (None = contributes silently)."""
    if member["observation_status"] in ("not_applicable", "register_only"):
        return None, None
    status = member["source_observability_status"]
    if status in BLOCKING_SOURCE:
        return "blocking_rows", status
    if status == "source_not_covering":
        return "excluded_rows", status
    if member["count"] == "":
        return "blocking_rows", member["extraction_status"]
    if member["coverage"] in LOWER_BOUND_COVERAGE:
        return "lower_bound_rows", member["coverage"]
    return None, None


def _expected_lists(members):
    lists = {"blocking_rows": [], "lower_bound_rows": [], "excluded_rows": []}
    for row_id, m in members.items():
        column, status = _classify(m)
        if column:
            lists[column].append(f"{row_id}:{status}")
    return {k: "; ".join(sorted(v)) for k, v in lists.items()}


def test_row_summed_equals_sum_of_row_cells_and_dedup_is_not_larger(pipeline_outputs):
    out = pipeline_outputs
    by_class = {}
    for p in out.platforms:
        if p["register_status"] == "quantified" and not p.get("provisional"):
            by_class.setdefault(str(p["initiation_class"]), []).append(str(p["row_id"]))
    seen_blank = seen_sum = seen_lower_bound = seen_excluded = False
    for cls, row_ids in by_class.items():
        for summed in out.cells("works_by_class_year", initiation_class=cls):
            year = summed["year"]
            members = {r: out.cell("works_by_row_year", row_id=r, year=year) for r in row_ids}
            expected = _expected_lists(members)
            for column, value in expected.items():
                assert summed[column] == value, (cls, year, column)
            contributing = [m for m in members.values()
                            if m["observation_status"] not in ("not_applicable", "register_only")
                            and m["source_observability_status"] != "source_not_covering"]
            if expected["blocking_rows"]:
                assert summed["count"] == "" and summed["observation_status"] == "not_observable"
                seen_blank = True
                continue
            if not contributing:
                # every in-range member is excluded: nothing to publish, never a zero (D-058)
                assert summed["count"] == "" and summed["source_observability_status"] == "source_not_covering"
                continue
            assert int(summed["count"]) == sum(int(m["count"]) for m in contributing)
            dedup = out.cell("unique_works_by_class_year", initiation_class=cls, year=year)
            assert int(dedup["count"]) <= int(summed["count"])
            assert {dedup[c] for c in ("blocking_rows", "lower_bound_rows", "excluded_rows")} == \
                {summed[c] for c in ("blocking_rows", "lower_bound_rows", "excluded_rows")}
            seen_sum = True
            seen_lower_bound |= bool(expected["lower_bound_rows"])
            seen_excluded |= bool(expected["excluded_rows"])
    assert seen_blank and seen_sum and seen_lower_bound and seen_excluded


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
    assert cell["lower_bound_rows"] == "" and cell["excluded_rows"] == "" and cell["coverage"] == "complete"


def test_partial_coverage_member_publishes_group_as_lower_bound_and_footnote_names_it(pipeline_outputs):
    """D-061: partial_coverage members no longer blank a group cell; they are named in lower_bound_rows."""
    out = pipeline_outputs
    # community_initiated 2024: prereview (1) and qeios_external_works (2) carry data_status partial_coverage
    cell = out.cell("works_by_class_year", initiation_class="community_initiated", year=2024)
    assert cell["count"] == "3" and cell["observation_status"] == "observed"
    assert cell["blocking_rows"] == ""
    assert cell["lower_bound_rows"] == "prereview:partial_coverage; qeios_external_works:partial_coverage"
    assert cell["coverage"] == "partial_coverage" and cell["temporal_coverage_status"] == "partial"
    dedup = out.cell("unique_works_by_class_year", initiation_class="community_initiated", year=2024)
    assert dedup["count"] == "2"          # one work is shared by prereview and qeios_external_works
    assert dedup["lower_bound_rows"] == cell["lower_bound_rows"]
    md = (out.tables / "works_by_class_year.md").read_text(encoding="utf-8")
    assert "Lower-bound group cells (D-061)" in md and "- community_initiated, 2024: " in md
    assert "prereview:partial_coverage" in md
    assert "Blank group cells (D-038)" in md     # author_initiated cells are still blocked in the fixture


def test_source_not_covering_member_publishes_group_and_is_listed_as_excluded(pipeline_outputs):
    """D-061: a row the source does not carry is excluded from the group cell and named, the cell publishes."""
    out = pipeline_outputs
    cell = out.cell("works_by_class_year", initiation_class="mixed", year=2023)
    assert cell["count"] == "1" and cell["blocking_rows"] == "" and cell["lower_bound_rows"] == ""
    assert cell["excluded_rows"] == ("life_science_editors:source_not_covering; "
                                     "life_science_editors_foundation:source_not_covering; "
                                     "the_unjournal:source_not_covering")
    assert cell["coverage"] == "partial_coverage"
    # the excluded row's own cell is untouched (D-058)
    own = out.cell("works_by_row_year", row_id="the_unjournal", year=2023)
    assert own["count"] == "" and own["source_observability_status"] == "source_not_covering"
    # all in-range members excluded: nothing to publish, never a zero
    only_excluded = out.cell("works_by_class_year", initiation_class="community_initiated", year=2018)
    assert only_excluded["count"] == "" and only_excluded["observation_status"] == "not_observable"
    assert only_excluded["source_observability_status"] == "source_not_covering"
    assert only_excluded["blocking_rows"] == "" and only_excluded["excluded_rows"] == "prelights:source_not_covering"


def test_blocking_statuses_still_blank_the_group(pipeline_outputs):
    """selector_no_match / unknown_scope / pending_run / incomplete keep the cell blank (D-061)."""
    out = pipeline_outputs
    cell = out.cell("works_by_class_year", initiation_class="author_initiated", year=2024)
    assert cell["count"] == "" and cell["observation_status"] == "not_observable"
    assert "access_microbiology:unknown_scope" in cell["blocking_rows"]
    assert "scipost:selector_no_match" in cell["blocking_rows"]
    # the other lists are still filled so that the reader sees the whole picture
    assert "qeios_hosted_works:partial_coverage" in cell["lower_bound_rows"]  # D-062: gates_open_research is machine_readable
    assert "metaror:source_not_covering" in cell["excluded_rows"]
    # observed_zero and not_applicable members appear in no list
    for r in out.table("works_by_class_year"):
        for column in ("blocking_rows", "lower_bound_rows", "excluded_rows"):
            for entry in filter(None, r[column].split("; ")):
                status = entry.split(":")[1]
                assert status not in ("observed_zero", "not_applicable", "observable", "complete")


def test_group_list_statuses_are_from_the_closed_vocabulary(pipeline_outputs):
    out = pipeline_outputs
    allowed = {"blocking_rows": {"unknown_scope", "pending_run", "selector_no_match", "incomplete", "failed"},
               "lower_bound_rows": {"partial_coverage", "partial_known_scope"},
               "excluded_rows": {"source_not_covering"}}
    for name in ("works_by_class_year", "works_by_configuration_year", "unique_works_by_class_year",
                 "unique_works_by_configuration_year", "unique_works_all_rows_year"):
        for r in out.table(name):
            blocking = [e for e in r["blocking_rows"].split("; ") if e]
            if blocking:
                assert r["count"] == "", (name, r)
            elif r["count"] == "":
                assert r["source_observability_status"] == "source_not_covering" and r["excluded_rows"], (name, r)
            for column, statuses in allowed.items():
                for e in filter(None, r[column].split("; ")):
                    row_id, status = e.split(":")
                    assert status in statuses and row_id, (name, column, e)
            if r["count"] != "":
                lower = {e.split(":")[1] for e in filter(None, r["lower_bound_rows"].split("; "))}
                if r["excluded_rows"] or "partial_coverage" in lower:
                    assert r["coverage"] == "partial_coverage", (name, r)
                elif lower:
                    assert r["coverage"] == "partial_known_scope", (name, r)
                else:
                    assert r["coverage"] in ("complete", "year_to_date"), (name, r)


def test_all_rows_class_attribution_sums_to_count(pipeline_outputs):
    """D-061 invariant: the three by-earliest-event class counts sum to the deduplicated all-rows count."""
    out = pipeline_outputs
    by_row = out.table("unique_works_all_rows_by_row_year")
    for r in out.table("unique_works_all_rows_year"):
        if r["count"] == "":
            continue
        classes = ("author_initiated", "community_initiated", "mixed")
        assert sum(int(r[f"n_{c}_by_earliest_event"]) for c in classes) == int(r["count"])
        for c in classes:
            attributed = [b for b in by_row if b["year"] == r["year"] and b["initiation_class"] == c and b["count"] != ""]
            assert sum(int(b["count"]) for b in attributed) == int(r[f"n_{c}_by_earliest_event"])
    # the by-row table is run-relative attribution: one line per quantified row and year in range
    for b in by_row:
        own = out.cell("works_by_row_year", row_id=b["row_id"], year=b["year"])
        assert own["observation_status"] != "not_applicable"
        assert (b["count"] == "") == (own["count"] == "")
        if b["count"] != "":
            assert int(b["count"]) <= int(own["count"])


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
    # the all-rows cell for 2024 is blank in the fixture run (selector_no_match / unknown_scope members) and says
    # why; the partial_coverage members are no longer a reason (D-061) and are listed as the lower bound
    all_2024 = out.cell("unique_works_all_rows_year", year=2024)
    assert all_2024["count"] == "" and "selector_no_match" in all_2024["blocking_rows"]
    assert "partial_coverage" not in all_2024["blocking_rows"]
    assert "prereview:partial_coverage" in all_2024["lower_bound_rows"]
    # the by-row attribution table still shows the earliest-event attribution of the shared work
    by_row = {b["row_id"]: b for b in out.table("unique_works_all_rows_by_row_year") if b["year"] == "2024"}
    assert by_row["prereview"]["count"] == "1" and by_row["qeios_external_works"]["count"] == "1"


def test_markdown_tables_mirror_csv(pipeline_outputs):
    out = pipeline_outputs
    for csv_path in sorted(out.tables.glob("*.csv")):
        md = (out.tables / (csv_path.stem + ".md")).read_text(encoding="utf-8")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            n_rows = sum(1 for _ in csv.DictReader(handle))
        assert md.count("\n| ") - 1 == n_rows, csv_path.name      # header line + data lines
        assert "Analysis cutoff: 2026-09-30" in md and "year_to_date" in md and "Additivity" in md
