"""Unit tests for callout_specs.py builders.

All MCP calls are mocked — no game, no API keys, no subprocess.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from src.voice_pipeline.callout_specs import (
    build_callout_message,
)


def _make_agent(context_frame: dict | None = None, leaderboard: dict | None = None):
    """Return a minimal agent mock whose MCP tool returns preset data."""
    agent = MagicMock()
    agent._mcp_lock = MagicMock()
    agent._mcp_lock.__aenter__ = AsyncMock(return_value=None)
    agent._mcp_lock.__aexit__ = AsyncMock(return_value=None)

    ctx = context_frame or {}
    lb = leaderboard or {}

    async def _call_tool(name):
        data = ctx if name == "get_context_frame" else lb
        obj = MagicMock()
        obj.text = json.dumps(data)
        return [obj]

    agent._mcp_tool = MagicMock()
    agent._mcp_tool.call_tool = AsyncMock(side_effect=_call_tool)
    return agent


def _make_monitor(last_damage: dict | None = None):
    monitor = MagicMock()
    monitor._last_damage_levels = dict(last_damage) if last_damage else {}
    return monitor


def _make_entry(code: str, involves_player: bool = False, details: dict | None = None) -> dict:
    return {
        "code": code,
        "eventName": code,
        "details": details or {},
        "involvesPlayer": involves_player,
        "severity": "critical",
    }


class TestRDFL:
    def test_rdfl_always_fires(self):
        agent = _make_agent()
        entry = _make_entry("RDFL")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "[CALLOUT]" in msg
        assert "red flag" in msg.lower()

    def test_rdfl_no_question(self):
        agent = _make_agent()
        entry = _make_entry("RDFL")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert "?" not in (msg or "")


class TestCHQF:
    def _ctx(self, current: int, start: int, total: int = 20) -> dict:
        return {
            "context": {
                "player": {
                    "position": {"current": current, "start": start, "total": total},
                    "car": {},
                }
            }
        }

    def _lb(self, penalties: list[str] | None = None) -> dict:
        return {
            "leaderboard": [
                {
                    "isPlayer": True,
                    "position": 1,
                    "unservedPenalties": penalties or [],
                }
            ]
        }

    def test_places_gained_message(self):
        agent = _make_agent(self._ctx(5, 10), self._lb())
        entry = _make_entry("CHQF")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "gained" in msg.lower()
        assert "encouraging" in msg.lower() or "positive" in msg.lower()

    def test_places_lost_message(self):
        agent = _make_agent(self._ctx(14, 8), self._lb())
        entry = _make_entry("CHQF")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "lost" in msg.lower()
        assert "review" in msg.lower() or "measured" in msg.lower()

    def test_unserved_penalty_in_facts(self):
        agent = _make_agent(self._ctx(5, 5), self._lb(["5s penalty"]))
        entry = _make_entry("CHQF")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "5s penalty" in msg

    def test_no_question(self):
        agent = _make_agent(self._ctx(5, 8), self._lb())
        entry = _make_entry("CHQF")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert "?" not in (msg or "")


class TestCOLL:
    def _ctx_with_damage(self, damage: dict) -> dict:
        return {
            "context": {"player": {"car": {"damageByPart": damage}, "position": {"current": 5}}}
        }

    def test_suppressed_when_no_damage_increase(self):
        # Cached levels same as current — no worsening
        current = {"frontWing": "undamaged", "rearWing": "undamaged", "floor": "undamaged"}
        agent = _make_agent(self._ctx_with_damage(current))
        monitor = _make_monitor(last_damage=current)
        entry = _make_entry("COLL", involves_player=True)
        msg = asyncio.run(build_callout_message(entry, agent, monitor=monitor))
        assert msg is None

    def test_fires_when_damage_reaches_medium(self):
        cached = {"frontWing": "undamaged", "rearWing": "undamaged"}
        current = {"frontWing": "medium", "rearWing": "undamaged"}
        agent = _make_agent(self._ctx_with_damage(current))
        monitor = _make_monitor(last_damage=cached)
        entry = _make_entry("COLL", involves_player=True)
        msg = asyncio.run(build_callout_message(entry, agent, monitor=monitor))
        assert msg is not None
        assert "front wing" in msg.lower()

    def test_box_advice_for_high_damage(self):
        cached = {"frontWing": "undamaged"}
        current = {"frontWing": "high"}
        agent = _make_agent(self._ctx_with_damage(current))
        monitor = _make_monitor(last_damage=cached)
        entry = _make_entry("COLL", involves_player=True)
        msg = asyncio.run(build_callout_message(entry, agent, monitor=monitor))
        assert msg is not None
        assert "box" in msg.lower()

    def test_cache_updated_after_call(self):
        cached = {"frontWing": "undamaged"}
        current = {"frontWing": "medium"}
        agent = _make_agent(self._ctx_with_damage(current))
        monitor = _make_monitor(last_damage=cached)
        entry = _make_entry("COLL", involves_player=True)
        asyncio.run(build_callout_message(entry, agent, monitor=monitor))
        assert monitor._last_damage_levels == current

    def test_rival_collision_fires_always(self):
        agent = _make_agent({"context": {"player": {"car": {"damageByPart": {}}}}})
        monitor = _make_monitor()
        entry = _make_entry("COLL", involves_player=False)
        msg = asyncio.run(build_callout_message(entry, agent, monitor=monitor))
        assert msg is not None

    def test_no_monitor_does_not_crash(self):
        # Without a monitor, COLL builder sees empty cache → fires if any damage at/above threshold
        current = {"frontWing": "medium"}
        agent = _make_agent({"context": {"player": {"car": {"damageByPart": current}}}})
        entry = _make_entry("COLL", involves_player=True)
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None  # no cached → medium is increase from "undamaged"


class TestRTMT:
    def test_player_retirement_contains_reason(self):
        agent = _make_agent()
        entry = _make_entry("RTMT", involves_player=True, details={"reasonName": "Terminal damage"})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "Terminal damage" in msg
        assert "[CALLOUT]" in msg

    def test_rival_retirement_contains_reason(self):
        agent = _make_agent()
        entry = _make_entry(
            "RTMT", involves_player=False, details={"reasonName": "Mechanical failure"}
        )
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "Mechanical failure" in msg


class TestSCAR:
    def test_formation_sc_suppressed(self):
        agent = _make_agent()
        entry = _make_entry(
            "SCAR",
            details={
                "safetyCarTypeName": "Formation Lap Safety Car",
                "eventTypeName": "Deployed",
            },
        )
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is None

    def test_full_sc_box_instruction(self):
        agent = _make_agent()
        entry = _make_entry(
            "SCAR",
            details={
                "safetyCarTypeName": "Full Safety Car",
                "eventTypeName": "Deployed",
            },
        )
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "box" in msg.lower()

    def test_virtual_sc_delta_instruction(self):
        agent = _make_agent()
        entry = _make_entry(
            "SCAR",
            details={
                "safetyCarTypeName": "Virtual Safety Car",
                "eventTypeName": "Deployed",
            },
        )
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "delta" in msg.lower()
        assert "box" not in msg.lower()

    def test_sc_returning_no_box(self):
        agent = _make_agent()
        entry = _make_entry(
            "SCAR",
            details={
                "safetyCarTypeName": "Full Safety Car",
                "eventTypeName": "Returning",
            },
        )
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "box" not in msg.lower()


class TestDRSE:
    def test_drse_mentions_drs(self):
        agent = _make_agent()
        entry = _make_entry("DRSE")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "drs" in msg.lower()


class TestFTLP:
    def test_player_fastest_lap_congratulates(self):
        agent = _make_agent()
        entry = _make_entry("FTLP", involves_player=True, details={"lapTimeFormatted": "83.962s"})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "83.962s" in msg
        assert "congratulate" in msg.lower() or "fastest" in msg.lower()

    def test_rival_fastest_lap(self):
        agent = _make_agent()
        entry = _make_entry("FTLP", involves_player=False, details={"lapTimeFormatted": "82.1s"})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "rival" in msg.lower() or "fastest" in msg.lower()


class TestGenericFallback:
    def test_unknown_code_uses_generic(self):
        agent = _make_agent()
        entry = {"code": "UNKN", "eventName": "Some Event", "details": {}, "involvesPlayer": False}
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "[CALLOUT]" in msg
        assert "Some Event" in msg
