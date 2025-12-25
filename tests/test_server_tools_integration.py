import os
import sys
from pathlib import Path
import asyncio
import socket
import contextlib
import pytest

# Ensure project root is on sys.path for direct module import
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _port_open(url: str) -> bool:
    try:
        if url.startswith("http://"):
            url = url[len("http://") :]
        host, port = url.split(":", 1)
        port = int(port)
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(0.25)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


@pytest.mark.skipif(
    not os.environ.get("F1_MCP_URL") and not _port_open("127.0.0.1:20915"),
    reason="F1 MCP server not reachable; set F1_MCP_URL or run server",
)
def test_basic_tools_roundtrip():
    pytest.importorskip("fastmcp")
    from f1_telemetry_mcp_client import F1TelemetryClient

    url = os.getenv("F1_MCP_URL") or "http://127.0.0.1:20915"

    async def _run():
        async with F1TelemetryClient(url=url) as client:
            session = await client.a_get_session_info()
            assert isinstance(session, dict)
            assert "lastUpdate" in session

            standings = await client.a_get_race_standings(limit=5)
            assert isinstance(standings, list)
            assert len(standings) <= 5

            summary = await client.a_get_race_summary()
            assert isinstance(summary, dict)
            for k in ("session", "topDrivers", "playerCar", "recentEvents"):
                assert k in summary

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.environ.get("F1_MCP_URL") and not _port_open("127.0.0.1:20915"),
    reason="F1 MCP server not reachable; set F1_MCP_URL or run server",
)
def test_history_tools_do_not_error():
    pytest.importorskip("fastmcp")
    from f1_telemetry_mcp_client import F1TelemetryClient

    url = os.getenv("F1_MCP_URL") or "http://127.0.0.1:20915"
    async def _run():
        async with F1TelemetryClient(url=url) as client:
            # These may be empty depending on when called; just assert shape
            tel = await client.a_get_car_telemetry_history(0, limit=3)
            assert isinstance(tel, list)

            st = await client.a_get_car_status_changes(0, limit=3)
            assert isinstance(st, list)

            dmg = await client.a_get_car_damage_events(0, limit=3)
            assert isinstance(dmg, list)

            laps = await client.a_get_car_lap_history(0, limit=3)
            assert isinstance(laps, list)

            sess = await client.a_get_session_changes(limit=3)
            assert isinstance(sess, list)

    asyncio.run(_run())
