"""D-050: title families are tested against the register-loaded expression."""
import re

import pytest

from src.common.register import load_platforms


# Eight observed families, with singular/plural and apostrophe variants.
POSITIVE_TITLES = [
    "Peer Review of “Synthetic article”",
    "Peer Review for “Synthetic article”",
    "Peer Review “Synthetic article”",
    "Authors' Response to Peer Reviews of “Synthetic article”",
    "Authors’ Response to Peer Reviews of “Synthetic article”",
    "Author Response to Peer Reviews of “Synthetic article”",
    "Author’s Response to Peer Review Reports for “Synthetic article”",
    "Author’s Responses to Peer Review Reports for “Synthetic article”",
    "Author’s Response to Peer Review Reports on “Synthetic article”",
    "Author’s Responses to Peer Review Reports on “Synthetic article”",
    "Authors’ Response to the Peer Review of “Synthetic article”",
    "Author’s Response to a Commentary on “Synthetic article”",
    "Author's Response to Peer Reviews of “Synthetic article”",
    "Authors Responses to Peer Reviews of “Synthetic article”",
]
NEGATIVE_TITLES = [
    # R1 residuals 10.2196/57116, 10.2196/29878 and 10.2196/29879.
    "Author’s Reponse to Peer Reviews of “Insider Threats to the Military Health System”",
    "Correction: Authors’ Response to Peer Reviews of “Impact of COVID-19 Testing Strategies”",
    "Correction: Author’s Responses to Peer Reviews of “Forecasting the COVID-19 Pandemic”",
    "Correction: Synthetic article",
    "Commentary on “Synthetic article”",
    "Synthetic article about patient outcomes",
    "Peer Reviewer training and clinical outcomes",
    "Author Response",
]


@pytest.mark.parametrize("row_id", ["jmirx_med", "jmirx_bio"])
@pytest.mark.parametrize("title,expected",
                         [(t, True) for t in POSITIVE_TITLES]
                         + [(t, False) for t in NEGATIVE_TITLES])
def test_companion_title_families_from_register_loader(row_id, title, expected):
    row = next(row for row in load_platforms() if row["row_id"] == row_id)
    pattern = row["extraction_selector"]["crossref"]["companion_title_regex"]
    assert "\x08" not in pattern, "YAML must preserve the regex word boundary"
    assert bool(re.search(pattern, title, re.IGNORECASE)) is expected
