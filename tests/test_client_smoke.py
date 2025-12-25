import os
import sys
from pathlib import Path
import pytest

# Ensure project root is on sys.path for direct module import
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_builds_default_url():
    from f1_telemetry_mcp_client import F1TelemetryClient

    c = F1TelemetryClient()
    assert c.url.startswith("http://")
    assert ":" in c.url


def test_env_url_overrides_default(monkeypatch):
    from f1_telemetry_mcp_client import F1TelemetryClient

    monkeypatch.setenv("F1_MCP_URL", "http://localhost:12345")
    c = F1TelemetryClient()
    assert c.url == "http://localhost:12345"
