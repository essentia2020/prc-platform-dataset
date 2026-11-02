"""The stage order is fixed and selectable only as a subsequence."""

from src import run_pipeline as rp


def test_stage_order_is_fixed():
    assert list(rp.STAGE_NAMES) == [
        "extract_crossref_works",
        "extract_crossref_peer_reviews",
        "extract_sciety_evaluations",
        "normalise",
        "analyse",
        "openalex_diagnostics",
        "report",
    ]


def test_selection_keeps_canonical_order():
    selected = rp.select_stages("report,extract_crossref_works")
    assert [s[0] for s in selected] == ["extract_crossref_works", "report"]


def test_no_stage_is_optional():
    assert [name for name, _, optional in rp.STAGES if optional] == []


def test_every_stage_module_exposes_run():
    import importlib
    for _, module_path, _ in rp.STAGES:
        assert callable(getattr(importlib.import_module(module_path), "run"))

def test_force_new_walk_reaches_walk_based_stages_only():
    names = [stage[0] for stage in rp.STAGES]
    walk_based = {n for n in names if n.startswith("extract_")} | {"openalex_diagnostics"}
    assert rp.FORCE_WALK_STAGES == frozenset(walk_based)
    assert not any(n in rp.FORCE_WALK_STAGES for n in ("normalise", "analyse", "report"))
