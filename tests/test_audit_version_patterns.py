"""R2: positive and negative examples for the version/lineage matcher.

All example strings that contain R2 or R3 patterns are wrapped in
``audit-fixture`` markers so that the self-audit of this file is span-based.
"""

from __future__ import annotations

import pytest


def _r2(engine, text, path="docs/x.md"):
    return [h for h in engine.scan(text, path) if h.rule == "R2"]


# audit-fixture: begin
POSITIVE = [
    "This dataset supersedes release 1.3.2 of the series.",
    "Compared with the earlier version 2.0 the register grew.",
    "v0.9 of this dataset had fewer rows.",
    "See the changelog for details.",
    "The legacy selector is kept for reference.",
    "Migration from the previous release is not supported.",
    "Upgrade notes for the previous dataset.",
    "See the version history of the archive.",
]
NEGATIVE = [
    "Requires Python 3.10 or later.",
    "PyYAML 6.0 and pandas 2.2 are pinned.",
    "cff-version: 1.2.0",
    "DOI 10.21468/scipost.1.2 refers to a published article in the dataset.",
    "The threshold is 2.5 stars across four reviews in this release.",
    "Average ratings of 3.0 ratings or higher, dataset rule.",
    "PRC Platform Dataset 1.4.0 is the current release.",
    "Release v1.4.0 is this dataset.",
    "Prefix 10.32388 is used by the dataset.",
    "Section 4.1 describes the interim files.",
    "The Version of Record is published later; versions never add counts.",
    "A previous page cursor is retried; earlier pages remain immutable.",
]
MIXED_FIXTURE_13 = (
    "Review DOI 10.1234/abcd.5 was issued; the threshold is 2.5 ratings; "
    "requires Python 3.11; this dataset replaces release 1.2.3."
)
# audit-fixture: end


@pytest.mark.parametrize("text", POSITIVE)
def test_positive_examples_are_hits(engine, text):
    assert _r2(engine, text), text


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative_examples_are_clean(engine, text):
    assert _r2(engine, text) == [], text


def test_fixture_13_reports_only_the_prohibited_dataset_version(engine):
    hits = _r2(engine, MIXED_FIXTURE_13)
    assert [h.matched for h in hits] == ["1.2.3"]


def test_requirements_and_pyproject_are_exempt(engine):
    # audit-fixture: begin
    text = "requests>=2.31  # dataset release pin\n"
    # audit-fixture: end
    assert _r2(engine, text, "requirements.txt") == []
    assert _r2(engine, text, "pyproject.toml") == []
    assert _r2(engine, text, "docs/x.md")


def test_fixture_markers_exempt_r2_spans_only(engine):
    # audit-fixture: begin
    unmarked = "previous release 0.1.0\n"
    # audit-fixture: end
    marked = "# audit-fixture: " + "begin\n" + unmarked + "# audit-fixture: " + "end\n"
    assert _r2(engine, marked, "tests/x.py") == []
    assert _r2(engine, unmarked, "tests/x.py")
