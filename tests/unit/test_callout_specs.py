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


class TestYELW:
    def test_immediate_risk_message(self):
        agent = _make_agent()
        entry = _make_entry("YELW", details={"immediateRisk": True})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "immediate" in msg.lower()
        assert "[CALLOUT]" in msg

    def test_no_immediate_risk(self):
        agent = _make_agent()
        entry = _make_entry("YELW", details={"immediateRisk": False})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "yellow" in msg.lower()
        assert "immediate" not in msg.lower()

    def test_no_details(self):
        agent = _make_agent()
        entry = _make_entry("YELW")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "[CALLOUT]" in msg


class TestDRSD:
    def test_drsd_with_reason(self):
        agent = _make_agent()
        entry = _make_entry("DRSD", details={"reasonName": "Crash ahead"})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "Crash ahead" in msg
        assert "DRS" in msg

    def test_drsd_without_reason(self):
        agent = _make_agent()
        entry = _make_entry("DRSD", details={})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "DRS" in msg


class TestPENA:
    def test_player_penalty_with_time(self):
        agent = _make_agent()
        entry = _make_entry("PENA", involves_player=True, details={"penaltyTypeName": "Time Penalty", "time": 5})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "5s" in msg
        assert "[CALLOUT]" in msg

    def test_player_penalty_no_time(self):
        agent = _make_agent()
        entry = _make_entry("PENA", involves_player=True, details={"penaltyTypeName": "Drive Through"})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "Drive Through" in msg

    def test_rival_penalty(self):
        agent = _make_agent()
        entry = _make_entry("PENA", involves_player=False, details={"penaltyTypeName": "Corner Cutting", "time": 10})
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "Rival" in msg or "rival" in msg
        assert "10s" in msg


class TestOVTK:
    def _ctx(self, player_id, current_pos=5):
        return {
            "context": {
                "player": {
                    "id": player_id,
                    "position": {"current": current_pos},
                }
            }
        }

    def _lb(self, rival_idx, rival_name):
        return {"leaderboard": [{"carIndex": rival_idx, "driver": rival_name, "isPlayer": False}]}

    def test_player_gained_place(self):
        ctx = self._ctx(player_id=0, current_pos=4)
        lb = self._lb(rival_idx=1, rival_name="Verstappen")
        agent = _make_agent(context_frame=ctx, leaderboard=lb)
        entry = {**_make_entry("OVTK"), "playerPitStatus": "none",
                 "details": {"overtakingVehicleIdx": 0, "beingOvertakenVehicleIdx": 1}}
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "gained" in msg.lower()
        assert "Verstappen" in msg

    def test_player_lost_place(self):
        ctx = self._ctx(player_id=0, current_pos=6)
        lb = self._lb(rival_idx=1, rival_name="Hamilton")
        agent = _make_agent(context_frame=ctx, leaderboard=lb)
        entry = {**_make_entry("OVTK"), "playerPitStatus": "none",
                 "details": {"overtakingVehicleIdx": 1, "beingOvertakenVehicleIdx": 0}}
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "lost" in msg.lower()

    def test_pitting_suppressed(self):
        ctx = self._ctx(player_id=0)
        agent = _make_agent(context_frame=ctx)
        entry = {**_make_entry("OVTK"), "playerPitStatus": "pitting",
                 "details": {"overtakingVehicleIdx": 0, "beingOvertakenVehicleIdx": 1}}
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is None

    def test_neither_slot_player_suppressed(self):
        ctx = self._ctx(player_id=0)
        agent = _make_agent(context_frame=ctx)
        entry = {**_make_entry("OVTK"), "playerPitStatus": "none",
                 "details": {"overtakingVehicleIdx": 3, "beingOvertakenVehicleIdx": 5}}
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is None


class TestLLAP:
    def _ctx(self, pos=2, total=20, gap_front=1.5, gap_back=0.8,
              front_driver="Hamilton", back_driver="Alonso"):
        return {
            "context": {
                "player": {
                    "position": {"current": pos, "total": total},
                    "gap": {
                        "frontS": gap_front,
                        "backS": gap_back,
                        "frontDriver": {"name": front_driver},
                        "backDriver": {"name": back_driver},
                    },
                }
            }
        }

    def test_llap_includes_position_and_gaps(self):
        agent = _make_agent(context_frame=self._ctx())
        entry = _make_entry("LLAP")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "[CALLOUT]" in msg
        assert "P2" in msg
        assert "Hamilton" in msg

    def test_llap_no_context_still_fires(self):
        agent = _make_agent(context_frame={})
        entry = _make_entry("LLAP")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "final lap" in msg.lower()


class TestCallMcpNoTool:
    def test_no_mcp_tool_returns_empty_dict(self):
        from src.voice_pipeline.callout_specs import _call_mcp
        agent = MagicMock()
        agent._mcp_tool = None

        async def _run():
            return await _call_mcp(agent, "get_context_frame")

        result = asyncio.run(_run())
        assert result == {}


class TestExtractDamageLevels:
    def test_missing_key_returns_empty(self):
        from src.voice_pipeline.callout_specs import _extract_damage_levels
        assert _extract_damage_levels({}) == {}
        assert _extract_damage_levels({"context": {}}) == {}

    def test_extracts_damage(self):
        from src.voice_pipeline.callout_specs import _extract_damage_levels
        ctx = {"context": {"player": {"car": {"damageByPart": {"frontWing": "medium"}}}}}
        result = _extract_damage_levels(ctx)
        assert result == {"frontWing": "medium"}


class TestGenericFallback:
    def test_unknown_code_uses_generic(self):
        agent = _make_agent()
        entry = {"code": "UNKN", "eventName": "Some Event", "details": {}, "involvesPlayer": False}
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "[CALLOUT]" in msg
        assert "Some Event" in msg

    def test_generic_with_penalty_details(self):
        agent = _make_agent()
        entry = {
            "code": "UNKN",
            "eventName": "Strange Event",
            "details": {"penaltyTypeName": "Stop Go", "time": 10},
            "involvesPlayer": True,
        }
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "Stop Go" in msg
        assert "10s" in msg
        assert "involving you" in msg

    def test_chqf_no_position_neutral_tone(self):
        # When neither current nor start position is available, diff is None → neutral tone
        ctx = {"context": {"player": {"position": {}, "car": {}}}}
        agent = _make_agent(context_frame=ctx, leaderboard={})
        entry = _make_entry("CHQF")
        msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        assert msg is not None
        assert "[CALLOUT]" in msg

    def test_builder_exception_falls_back_to_generic(self):
        from unittest.mock import patch, AsyncMock as AM
        agent = _make_agent()
        entry = _make_entry("RDFL")
        with patch(
            "src.voice_pipeline.callout_specs._build_rdfl",
            new=AM(side_effect=RuntimeError("boom")),
        ):
            msg = asyncio.run(build_callout_message(entry, agent, monitor=None))
        # Should fall back to generic, not crash
        assert msg is not None
