"""Unit tests for src/config.py: defaults, back-compat migration, error handling."""
import json
import pytest
from pathlib import Path


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Point config loader at a temp directory."""
    cfg_file = tmp_path / "config.json"
    import src.config as cfg_module
    monkeypatch.setattr(cfg_module, "_CONFIG_PATH", cfg_file)
    return cfg_file


def test_defaults_when_no_file(config_path):
    from src.config import load
    cfg = load()
    assert cfg["udpPort"] == 20777
    assert cfg["serverPort"] == 8080
    assert cfg["engineerCallouts"] == "critical"
    assert isinstance(cfg["sessionTypes"], list)


def test_explicit_values_override_defaults(config_path):
    config_path.write_text(json.dumps({"udpPort": 9999, "serverPort": 5000}))
    from src.config import load
    cfg = load()
    assert cfg["udpPort"] == 9999
    assert cfg["serverPort"] == 5000
    # unspecified keys still get defaults
    assert cfg["engineerCallouts"] == "critical"


def test_proactive_events_migrated_to_engineer_callouts(config_path):
    """Old config.json with proactiveEvents should be migrated transparently."""
    config_path.write_text(json.dumps({"proactiveEvents": "critical_relevant"}))
    from src.config import load
    cfg = load()
    assert cfg["engineerCallouts"] == "critical_relevant"
    assert "proactiveEvents" not in cfg


def test_engineer_callouts_not_overwritten_if_already_present(config_path):
    """If both keys exist (shouldn't happen, but guard), engineerCallouts wins."""
    config_path.write_text(json.dumps({
        "engineerCallouts": "off",
        "proactiveEvents": "critical_relevant",
    }))
    from src.config import load
    cfg = load()
    assert cfg["engineerCallouts"] == "off"


def test_corrupt_file_falls_back_to_defaults(config_path):
    config_path.write_text("{{not valid json}}")
    from src.config import load
    cfg = load()
    assert cfg["udpPort"] == 20777
    assert cfg["engineerCallouts"] == "critical"


def test_get_helper_returns_default(config_path, monkeypatch):
    config_path.write_text("{}")
    from src import config as cfg_module
    assert cfg_module.get("engineerCallouts", "fallback") == "critical"
    assert cfg_module.get("nonexistent_key", "fallback") == "fallback"
