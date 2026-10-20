"""R1: private-token matching with placeholder tokens.

Placeholder tokens are synthetic (see tests/conftest.py); real tokens never
appear in the repository.
"""

from __future__ import annotations

from tools import audit_text


def _rules(hits):
    return sorted({h.rule for h in hits})


def test_token_is_case_insensitive_by_default(engine):
    hits = engine.scan("Text mentioning PlaceholderTokenAlpha here.", "docs/x.md")
    assert [h.rule for h in hits] == ["R1"]


def test_multi_word_token_matches_across_whitespace(engine):
    hits = engine.scan("a placeholder\n   phrase   beta b", "docs/x.md")
    assert [h.rule for h in hits] == ["R1"]


def test_word_boundaries_prevent_substring_hits(engine):
    assert engine.scan("placeholdertokenalphabet is not the token", "docs/x.md") == []
    assert engine.scan("xplaceholdertokenalpha", "docs/x.md") == []


def test_abbreviation_tokens_are_case_sensitive(engine):
    assert [h.rule for h in engine.scan("code PTX1 here", "docs/x.md")] == ["R1"]
    assert engine.scan("code ptx1 here", "docs/x.md") == []
    assert [h.rule for h in engine.scan("PLH-2", "docs/x.md")] == ["R1"]


def test_r1_is_not_suppressed_by_fixture_markers(engine):
    text = "# audit-fixture: " + "begin\nplaceholdertokenalpha\n# audit-fixture: " + "end\n"
    assert [h.rule for h in engine.scan(text, "tests/fixtures/audit/x.py")] == ["R1"]


def test_r1_is_not_suppressed_by_dependency_or_doi_context(engine):
    text = "Python 3.12 placeholdertokenalpha 10.1234/placeholdertokenalpha"
    hits = engine.scan(text, "docs/x.md")
    assert [h.rule for h in hits] == ["R1", "R1"]


def test_r1_applies_to_the_audit_tool_and_version_tests(engine):
    for path in ("tools/audit_text.py", "tests/test_audit_version_patterns.py"):
        hits = engine.scan("x = 'placeholdertokenalpha'\n", path)
        assert [h.rule for h in hits] == ["R1"], path


def test_citation_file_reference_with_private_token_is_still_reported(engine_factory):
    """Boundary fixture 14: an allowed citation plus a private token in
    CITATION.cff — the citation is exempt (R3 allow-list), the token is not."""
    # audit-fixture: begin
    cff = (
        "cff-version: 1.2.0\n"
        "references:\n"
        "  - type: article\n"
        "    title: \"Example title\"\n"
        "    authors:\n"
        "      - family-names: Corker\n"
        "        given-names: K.\n"
        "    notes: \"placeholdertokenalpha\"\n"
    )
    # audit-fixture: end
    allow = [audit_text.AllowEntry("R3", "CITATION.cff", yaml_path="references[*].authors[*].family-names")]
    hits = engine_factory(allow).scan(cff, "CITATION.cff")
    assert _rules(hits) == ["R1"]
    assert all(h.matched.lower() == "placeholdertokenalpha" for h in hits)


def test_commit_message_scope_includes_tokens(engine):
    hits = engine.scan("Add register\n\nmentions placeholder phrase beta", "<commit-message abc>")
    assert [h.rule for h in hits] == ["R1"]
