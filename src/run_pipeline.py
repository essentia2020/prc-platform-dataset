"""Single entry point of the pipeline; fixes the stage order.

Usage (run locally by the dataset maintainer, never in an automated preview):

    python -m src.run_pipeline --stages all
    python -m src.run_pipeline --stages extract_crossref_works,extract_sciety_evaluations
    python -m src.run_pipeline --list

Stage order (fixed; later stages consume the outputs of earlier ones):

    1. extract_crossref_works        -> data/raw/crossref/works/…, data/interim/crossref_works__<row_id>.csv
    2. extract_crossref_peer_reviews -> data/raw/crossref/peer_reviews/…, data/interim/crossref_peer_reviews__<row_id>.csv
    3. extract_sciety_evaluations    -> data/raw/sciety/…, data/interim/sciety_evaluations__<group>.csv
    4. normalise                     -> data/interim/*__normalised.csv (only when src/normalise exists)
    5. analyse                       -> data/processed/*.csv, reports/tables/*.csv|md
    6. report                        -> reports/figures/*.png|svg, reports/CHECKSUMS.txt

Each stage is a module exposing ``run(run_config, sources_config, platforms,
logger)``.  Every stage is mandatory: a missing module makes the stage fail
loudly with ``NotImplementedError``; nothing is skipped silently.  Stage 5
reads the record-level files written by Stage 4, so ``normalise`` must run
(or have run for the same ``run_id``) before ``analyse``.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Callable, Sequence

from src.common.config import load_run_config, load_sources_config
from src.common.log import JsonlLogger
from src.common.register import load_platforms

STAGES: Sequence[tuple[str, str, bool]] = (
    # (stage name, module path, optional)
    ("extract_crossref_works", "src.extract.crossref_works", False),
    ("extract_crossref_peer_reviews", "src.extract.crossref_peer_reviews", False),
    ("extract_sciety_evaluations", "src.extract.sciety_evaluations", False),
    ("normalise", "src.normalise.clean_and_normalise", False),
    ("analyse", "src.analyse.build_aggregates", False),
    ("report", "src.report.make_reports", False),
)

STAGE_NAMES: Sequence[str] = tuple(name for name, _, _ in STAGES)


def _resolve(module_path: str, optional: bool) -> Callable | None:
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if optional and exc.name == module_path:
            return None
        raise NotImplementedError(f"stage module {module_path} is not available") from exc
    run = getattr(module, "run", None)
    if run is None:
        raise NotImplementedError(f"stage module {module_path} has no run() function")
    return run


def select_stages(requested: str) -> list[tuple[str, str, bool]]:
    """Return the requested stages in canonical order; ``all`` selects every stage."""
    if requested == "all":
        return list(STAGES)
    wanted = [s.strip() for s in requested.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in STAGE_NAMES]
    if unknown:
        raise SystemExit(f"unknown stage(s): {unknown}; known stages: {list(STAGE_NAMES)}")
    return [stage for stage in STAGES if stage[0] in wanted]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stages", default="all", help="comma-separated stage names or 'all'")
    parser.add_argument("--list", action="store_true", help="print the stage order and exit")
    parser.add_argument("--force-new-walk", action="store_true",
                        help="extraction stages: start a new walk even when a complete walk exists for the run")
    args = parser.parse_args(argv)

    if args.list:
        for position, (name, module_path, optional) in enumerate(STAGES, start=1):
            flag = " (optional)" if optional else ""
            print(f"{position}. {name:<32} {module_path}{flag}")
        return 0

    run_config = load_run_config()
    sources_config = load_sources_config()
    platforms = load_platforms()
    logger = JsonlLogger(run_config.run_id)
    logger.event("pipeline_start", stages=[s[0] for s in select_stages(args.stages)])

    for name, module_path, optional in select_stages(args.stages):
        run = _resolve(module_path, optional)
        if run is None:
            logger.event("stage_skipped", stage=name, reason="optional module absent")
            print(f"[skip] {name}: optional module {module_path} absent")
            continue
        logger.event("stage_start", stage=name)
        print(f"[run ] {name}")
        options = {"force_new_walk": True} if (args.force_new_walk and name.startswith("extract_")) else {}
        try:
            run(run_config, sources_config, platforms, logger, **options)
        except Exception as exc:  # a stage failure stops the pipeline loudly
            logger.event("stage_failed", stage=name, error=f"{type(exc).__name__}: {exc}")
            print(f"[fail] {name}: {exc}", file=sys.stderr)
            return 1
        logger.event("stage_end", stage=name)
    logger.event("pipeline_end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
