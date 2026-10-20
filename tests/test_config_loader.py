"""config/run.yaml loader fails loudly on missing or malformed fields."""

import datetime as dt

import pytest
import yaml

from src.common import config


def _write(tmp_path, data):
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


BASE = {
    "run_id": "run_test_01",
    "analysis_cutoff_date": "2025-12-31",
    "mailto": "someone@example.org",
    "selected_walk_policy": "latest_completed_then_smallest_walk_id",
}


def test_repository_run_config_loads():
    cfg = config.load_run_config()
    assert cfg.run_id and cfg.mailto and cfg.analysis_cutoff_date


@pytest.mark.parametrize("missing", sorted(BASE))
def test_missing_field_fails(tmp_path, missing):
    data = dict(BASE)
    del data[missing]
    with pytest.raises(config.ConfigError, match=missing):
        config.load_run_config(_write(tmp_path, data))


def test_year_end_cutoff_detected(tmp_path):
    cfg = config.load_run_config(_write(tmp_path, BASE))
    assert cfg.cutoff_is_year_end is True
    assert cfg.analysis_cutoff_date == dt.date(2025, 12, 31)


def test_mid_year_cutoff_is_partial(tmp_path):
    cfg = config.load_run_config(_write(tmp_path, {**BASE, "analysis_cutoff_date": "2025-09-30"}))
    assert cfg.cutoff_is_year_end is False


def test_invalid_date_fails(tmp_path):
    with pytest.raises(config.ConfigError, match="analysis_cutoff_date"):
        config.load_run_config(_write(tmp_path, {**BASE, "analysis_cutoff_date": "30/09/2025"}))


def test_unknown_walk_policy_fails(tmp_path):
    with pytest.raises(config.ConfigError, match="selected_walk_policy"):
        config.load_run_config(_write(tmp_path, {**BASE, "selected_walk_policy": "first"}))


def test_user_agent_contains_mailto(tmp_path):
    cfg = config.load_run_config(_write(tmp_path, BASE))
    assert "mailto:someone@example.org" in cfg.user_agent()
