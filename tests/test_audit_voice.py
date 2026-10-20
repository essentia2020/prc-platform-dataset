"""R4: author-voice rule, including the exact User-Agent exemption.

Flagged words are assembled from fragments so that this file does not
contain them literally (R4 has no fixture-marker exemption).
"""

from __future__ import annotations

import pytest

W = "".join(("w", "e"))
OUR = "".join(("o", "ur"))
US = "".join(("u", "s"))
THE_AUTHOR = "the " + "".join(("auth", "or"))
THE_TEAM = "the " + "".join(("te", "am"))
THE_RESEARCHER = "the " + "".join(("resear", "cher"))
ROLE_A = "".join(("ag", "ent"))
ROLE_B = "".join(("assis", "tant"))
TOOL_A = "".join(("Perp", "lexity"))
TOOL_B = "".join(("Comp", "uter"))


def _r4(engine, text, path="docs/x.md"):
    return [h for h in engine.scan(text, path) if h.rule == "R4"]


@pytest.mark.parametrize("text", [
    f"In this release {W} count works.",
    f"Counts follow {OUR} rules.",
    f"Let {US} define the series.",
    f"{THE_AUTHOR} verified the platforms.",
    f"{THE_TEAM} decided otherwise.",
    f"{THE_RESEARCHER} reserves the DOI.",
    f"The {ROLE_A} wrote the files.",
    f"An {ROLE_B} produced the table.",
    f"Built with {TOOL_A}.",
    f"Produced by {TOOL_B} on request.",
])
def test_voice_hits(engine, text):
    assert _r4(engine, text), text


@pytest.mark.parametrize("text", [
    "Set the User-Agent header to include the mailto address.",
    "Crossref reads the user agent string.",
    "The user agent is logged.",
    "Run `python -m src.run_pipeline --list` to print the stage order.",
    "We is not lowercase here: We, Our, Us are not matched.",
    "The authors of the evaluated work may respond.",
    "status and census contain the pronoun only as a substring.",
    "https://support.example.org/hc/en-" + US + "/articles/1 is a URL.",
    "user_agent_label is an identifier.",
])
def test_voice_negatives(engine, text):
    assert _r4(engine, text) == [], text


def test_user_agent_exemption_is_exact(engine):
    assert _r4(engine, f"the HTTP User-{ROLE_A.capitalize()} header") == []
    assert _r4(engine, f"a browsing {ROLE_A} of the service")


def test_r4_scope_excludes_licence_texts(engine):
    text = f"{OUR} licences permit sharing and adaptation with attribution."
    assert _r4(engine, text, "LICENSE-DATA") == []
    assert _r4(engine, text, "docs/x.md")


def test_r4_applies_to_python_docstrings(engine):
    assert _r4(engine, f'"""Here {W} load the config."""\n', "src/common/x.py")


def test_self_citation_in_neutral_voice_is_clean_but_third_person_is_reported(engine_factory):
    """Positive R4 fixture: the conceptual source for axis 2 is cited in
    first-person or neutral voice; third-person self-reference is a hit."""
    from tools import audit_text

    # audit-fixture: begin
    neutral = "The workflow-configuration axis follows Kochetkov (2026), which I wrote."
    third_person = f"The workflow-configuration axis follows Kochetkov (2026), {THE_AUTHOR}'s own article."
    allow = [audit_text.AllowEntry("R3", "README.md", literal="Kochetkov (2026)")]
    # audit-fixture: end
    engine = engine_factory(allow)
    assert engine.scan(neutral, "README.md") == []
    hits = engine.scan(third_person, "README.md")
    assert [h.rule for h in hits] == ["R4"]
