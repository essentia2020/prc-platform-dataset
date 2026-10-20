"""DOI normalisation and URL canonicalisation safeguards."""

import pytest

from src.common import identifiers as ids


def test_normalise_doi_strips_resolver_and_lowercases():
    assert ids.normalise_doi("https://doi.org/10.32388/ABC123.2") == "10.32388/abc123.2"
    assert ids.normalise_doi("doi:10.32388/ABC123") == "10.32388/abc123"


def test_normalise_doi_rejects_non_doi():
    with pytest.raises(ids.IdentifierError):
        ids.normalise_doi("not-a-doi")


def test_canonical_doi_strips_version_with_pattern_only():
    pattern = r"^(10\.32388/[a-z0-9]+)(?:\.\d+)?$"
    assert ids.canonical_doi("10.32388/abc123.2", pattern) == "10.32388/abc123"
    assert ids.canonical_doi("10.32388/abc123.2", None) == "10.32388/abc123.2"
    assert ids.canonical_doi("10.7554/elife.12345", pattern) == "10.7554/elife.12345"


def test_asserted_and_canonical_identifiers_stay_distinct():
    asserted = ids.work_id_from_doi(ids.normalise_doi("10.32388/ABC.2"))
    canonical = ids.work_id_from_doi(ids.canonical_doi(ids.bare_doi(asserted), r"^(10\.32388/[a-z0-9]+)(?:\.\d+)?$"))
    assert asserted == "doi:10.32388/abc.2"
    assert canonical == "doi:10.32388/abc"
    assert asserted != canonical


def test_url_canonicalisation_lowercases_host_only():
    url = "HTTPS://Example.ORG/Path/To/Item?Q=A&b=B#Frag/"
    assert ids.canonicalise_url(url) == "HTTPS://example.org/Path/To/Item?Q=A&b=B#Frag/"


def test_url_canonicalisation_preserves_trailing_slash_and_query():
    assert ids.canonicalise_url("https://a.org/x/") == "https://a.org/x/"
    assert ids.canonicalise_url("https://a.org/x") == "https://a.org/x"
    assert ids.canonicalise_url("https://a.org/x?y=1") != ids.canonicalise_url("https://a.org/x?y=2")


def test_url_canonicalisation_rejects_relative_url():
    with pytest.raises(ids.IdentifierError):
        ids.canonicalise_url("/relative/path")
