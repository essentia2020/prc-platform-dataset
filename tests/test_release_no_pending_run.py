"""D-039: ``pending_run`` is transient and must not survive into released tables."""

from pathlib import Path

from src.analyse.build_aggregates import PENDING_RUN, RowAnalysis, row_cells
from src.common.run_state import RowState

TABLES = Path(__file__).resolve().parents[1] / "reports" / "tables"


def test_released_tables_contain_no_pending_run():
    for path in sorted(TABLES.glob("*")):
        if path.is_file() and path.suffix in (".csv", ".md"):
            assert PENDING_RUN not in path.read_text(encoding="utf-8"), path


def test_pending_run_before_first_complete_run(pipeline_outputs):
    from datetime import date
    row = next(p for p in pipeline_outputs.platforms if p["row_id"] == "access_microbiology")
    state = RowState(row_id="access_microbiology", register_status="quantified",
                     primary_scopes={"crossref/works__10.1099__journal-article": "not_run"})
    a = RowAnalysis(row=row, state=state)
    a.eligible_start, a.eligible_end, a.start_unresolved = None, 2026, True
    cells = row_cells(a, [2018, 2019, 2024], date(2026, 9, 30))
    assert cells[2018].observation_status == "not_applicable"           # before launch
    assert cells[2024].source_observability_status == PENDING_RUN and cells[2024].count is None
    # after a complete run without events the status is unknown_scope instead
    assert pipeline_outputs.cell("works_by_row_year", row_id="access_microbiology", year=2024)[
        "source_observability_status"] == "unknown_scope"
