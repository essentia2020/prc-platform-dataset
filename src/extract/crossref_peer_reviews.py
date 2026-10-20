"""Stage ``extract_crossref_peer_reviews``: peer-review records and their targets.

One cursor walk per ``works__<prefix>__peer-review`` scope, including the
separate review prefixes declared by rows (``review_doi_prefix``).  Complete
walks are flattened to ``data/interim/crossref_peer_reviews__<row_id>.csv``
with one line per (review DOI, ``is-review-of`` target) and the target flags
``placeholder``, ``malformed``, ``self_reference`` or ``missing``.  Records
claimed by no row are kept in ``crossref_peer_reviews__unattributed__<prefix>.csv``.
"""

from __future__ import annotations

from .crossref_common import ExtractionIncomplete, run_crossref

__all__ = ["run", "ExtractionIncomplete"]


def run(run_config, sources_config, platforms, logger, **options):
    return run_crossref(run_config, sources_config, platforms, logger, kinds="reviews", **options)
