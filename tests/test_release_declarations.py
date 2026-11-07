"""Current-release declarations agree with src.__version__ and carry no stale
literal. These checks read the files directly and do not use the audit engine,
its allow-list or fixture markers."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from src import __version__
from src.common.config import RunConfig, load_sources_config

ROOT = Path(__file__).resolve().parents[1]
H1_FILES = {
    "README.md": "# PRC Platform Dataset {v}",
    "config/classification_scheme.md": "# Classification scheme — PRC Platform Dataset {v}",
    "config/platforms.yaml": "# Platform register — source of truth for PRC Platform Dataset {v}",
    "docs/analysis_plan.md": "# Analysis plan — PRC Platform Dataset {v}",
    "docs/data_dictionary.md": "# Data dictionary — PRC Platform Dataset {v} (schema)",
    "docs/decisions.md": "# Decision log — PRC Platform Dataset {v}",
    "docs/limitations.md": "# Limitations — PRC Platform Dataset {v}",
}


def test_pyproject_project_version():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_citation_declarations():
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["version"] == __version__
    assert cff["title"] == f"PRC Platform Dataset {__version__}"
    assert cff["doi"] == "10.5281/zenodo.24015301"


def test_document_title_lines():
    for rel, pattern in H1_FILES.items():
        first = (ROOT / rel).read_text(encoding="utf-8").splitlines()[0]
        assert first == pattern.format(v=__version__), rel

def test_license_data_scope_names_current_version():
    text = (ROOT / "LICENSE-DATA").read_text(encoding="utf-8")
    assert f"report files of PRC Platform Dataset {__version__}, namely everything under:" in text
    assert re.findall(r"PRC Platform Dataset (\d+\.\d+\.\d+)", text) == [__version__]


def test_no_stale_version_literal_in_active_configuration_or_source():
    stale = re.compile(rf"/(?!{re.escape(__version__)}\b)\d+\.\d+\.\d+\b")
    for rel in ["config/sources.yaml", "src/common/config.py", "src/common/http.py", "src/__init__.py"]:
        assert not stale.search((ROOT / rel).read_text(encoding="utf-8")), rel
    assert "{version}" in (ROOT / "config/sources.yaml").read_text(encoding="utf-8")


def test_runtime_user_agent_matches_release():
    config = RunConfig(
        run_id="run_test_01",
        analysis_cutoff_date=date(2026, 9, 30),
        mailto="offline@example.invalid",
        selected_walk_policy="latest_completed_then_smallest_walk_id",
        user_agent_label="prc-platform-dataset-tests",
    )
    expected = f"{config.user_agent_label}/{__version__} (mailto:{config.mailto})"
    assert config.user_agent() == expected
    template = load_sources_config()["http_defaults"]["user_agent_template"]
    assert template == "{label}/{version} (mailto:{mailto})"
    assert template.format(label=config.user_agent_label, version=__version__, mailto=config.mailto) == expected
