"""Stage ``extract_crossref_works``: journal-article and posted-content records.

One cursor walk per ``works__<prefix>__<type>`` scope declared by the
register; every response is stored immutably and recorded in the walk
manifest before the next request.  Complete walks are flattened to
``data/interim/crossref_works__<row_id>.csv``; incomplete or failed walks
write nothing and make the stage exit with an error that names the blocked
rows.  This module never aggregates.
"""

from __future__ import annotations

from .crossref_common import ExtractionIncomplete, run_crossref

__all__ = ["run", "ExtractionIncomplete"]


def run(run_config, sources_config, platforms, logger, **options):
    """Entry point used by ``src.run_pipeline``.

    ``options`` may carry ``raw_root``, ``manifest_root``, ``interim_root``,
    ``transport`` (offline tests), ``sleeper`` and ``force_new_walk``.
    """
    return run_crossref(run_config, sources_config, platforms, logger, kinds="works", **options)
