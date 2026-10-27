"""Explicit, documented work correspondences; titles never establish identity."""

from typing import Any, Mapping

from .identifiers import IdentifierError, canonical_doi, normalise_doi


def correspondence_index(row: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """Map the explicitly listed DOI records to their primary and evidence basis.

    The register stores a verified alias edge and a version-relation edge.
    This function validates that chain without making requests or inventing
    records/dates. Unlisted identifiers are never mapped by title or stem alone.
    """
    block = (row.get("extraction_selector") or {}).get("crossref") or {}
    out: dict[str, tuple[str, str]] = {}
    for entry in block.get("work_correspondences") or []:
        primary = normalise_doi(entry["primary_doi"])
        alias = normalise_doi(entry["alias_doi"])
        first = normalise_doi(entry["version_relation"]["from_doi"])
        target = normalise_doi(entry["version_relation"]["to_doi"])
        stem = str(entry["version_stem"])
        kind = entry["version_relation"]["type"]
        basis = entry["correspondence_basis"]
        if target != alias or kind not in ("new_version", "is-version-of", "has-version"):
            raise IdentifierError("work correspondence requires a version relation to the alias DOI")
        if basis != "version_stem+alias+relation":
            raise IdentifierError("work correspondence must record version_stem+alias+relation")
        # Match the platform stem, not the DOI registration prefix.
        for doi in (first, alias):
            suffix = doi.split("/", 1)[1]
            if suffix.rsplit(".", 1)[0] != stem or not suffix.rsplit(".", 1)[-1].isdigit():
                raise IdentifierError("version relation and alias must share the documented version stem")
        if not entry.get("evidence_urls") or len({primary, alias, first}) != 3:
            raise IdentifierError("work correspondence needs distinct identifiers and evidence URLs")
        for doi in (first, alias, primary):
            value = (primary, basis)
            if doi in out and out[doi] != value:
                raise IdentifierError(f"conflicting work correspondences for {doi}")
            out[doi] = value
    return out


def canonical_work_doi(row: Mapping[str, Any], doi: str) -> tuple[str, str]:
    """Return canonical DOI and correspondence basis without supplying a date."""
    doi = normalise_doi(doi)
    explicit = correspondence_index(row).get(doi)
    if explicit:
        return explicit
    return canonical_doi(doi, row.get("doi_version_pattern") or None), ""
