"""DOI and URL normalisation shared by extraction, normalisation and analysis.

Identifier syntax (work-level):

    doi:<lowercased-doi>
    url:<normalised-url>
    id:<source>:<identifier>

``normalise_doi`` lowercases and strips resolver prefixes but keeps any
version suffix and any repeated slash (asserted identifier).  ``canonical_doi``
collapses repeated slashes and additionally applies the platform-specific
``doi_version_pattern`` from ``config/platforms.yaml`` (canonical identifier).
``identifier_flag`` reports ``repeated_slash`` for the malformed source form.  URL canonicalisation lowercases the host only; the
scheme, path, query, fragment and trailing slash are preserved.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_DOI_RESOLVER_RE = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)
_DOI_SCHEME_RE = re.compile(r"^doi:", re.IGNORECASE)
_DOI_SHAPE_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_REPEATED_SLASH_RE = re.compile(r"/{2,}")
REPEATED_SLASH_FLAG = "repeated_slash"


class IdentifierError(ValueError):
    """Raised when a string cannot be interpreted as a DOI or URL identifier."""


def normalise_doi(raw: str) -> str:
    """Return the bare lowercased DOI (version suffix retained).

    Accepts ``https://doi.org/10.X/Y``, ``doi:10.X/Y`` and bare ``10.X/Y``
    forms; surrounding whitespace is removed.  Raises ``IdentifierError`` if
    the result does not have DOI shape, so that malformed targets are flagged
    rather than silently kept.
    """
    if raw is None:
        raise IdentifierError("DOI is None")
    doi = raw.strip()
    doi = _DOI_RESOLVER_RE.sub("", doi)
    doi = _DOI_SCHEME_RE.sub("", doi)
    doi = doi.strip().lower()
    if not _DOI_SHAPE_RE.match(doi):
        raise IdentifierError(f"not a DOI: {raw!r}")
    return doi


def has_repeated_slash(doi: str) -> bool:
    """True when the DOI string contains ``//`` (or longer runs) anywhere.

    Crossref accepts such strings at deposit (e.g. ``10.15694//mep.2021.000035.1``);
    they are malformed at source and never equal their single-slash form by
    string comparison.
    """
    return bool(_REPEATED_SLASH_RE.search(doi or ""))


def collapse_repeated_slashes(doi: str) -> str:
    """Return ``doi`` with every run of slashes reduced to one slash.

    Used for the *canonical* identifier only; the raw string is kept beside
    it (``doi_original`` / ``target_id_raw``) so the source defect stays visible.
    """
    return _REPEATED_SLASH_RE.sub("/", doi or "")


def identifier_flag(raw: str) -> str:
    """``repeated_slash`` when the raw DOI string has a run of slashes, else ``""``."""
    return REPEATED_SLASH_FLAG if has_repeated_slash(raw) else ""


def is_doi_like(raw: str) -> bool:
    try:
        normalise_doi(raw)
    except IdentifierError:
        return False
    return True


def canonical_doi(doi: str, version_pattern: str | None) -> str:
    """Strip a platform-specific version suffix from a normalised DOI.

    ``version_pattern`` is a regular expression whose first capture group is
    the canonical stem.  When the pattern is ``None`` or does not match, the
    DOI is returned unchanged (no guessing).
    """
    doi = collapse_repeated_slashes(doi)
    if not version_pattern:
        return doi
    match = re.match(version_pattern, doi)
    if match and match.lastindex:
        return match.group(1)
    return doi


def canonicalise_url(raw: str) -> str:
    """Lowercase the host of a URL; leave every other component untouched."""
    raw = raw.strip()
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise IdentifierError(f"not an absolute URL: {raw!r}")
    scheme = raw[: raw.index(":")]  # keep the scheme exactly as written
    host = parts.hostname or ""
    netloc = host.lower()
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    if parts.username:
        cred = parts.username + (f":{parts.password}" if parts.password else "")
        netloc = f"{cred}@{netloc}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def work_id_from_doi(doi: str) -> str:
    return f"doi:{doi}"


def work_id_from_url(url: str) -> str:
    return f"url:{canonicalise_url(url)}"


def work_id_from_source_id(source: str, identifier: str) -> str:
    return f"id:{source}:{identifier}"


def bare_doi(work_id: str) -> str:
    """Return the DOI part of a ``doi:`` identifier, else an empty string."""
    return work_id[4:] if work_id.startswith("doi:") else ""
