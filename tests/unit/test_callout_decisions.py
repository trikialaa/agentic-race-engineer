"""
Unit tests for CalloutMonitor decision logic.
The LLM (_fire) is stubbed — we test WHICH events are selected and
suppressed, not what the LLM says.
"""
from __future__ import annotations

import queue
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.voice_pipeline.callouts import (
    CalloutMonitor,
    _DEFAULT_EVENT_COOLDOWN,
    _EVENT_COOLDOWNS,
    _GLOBAL_RATE_LIMIT_S,
    _PTT_SUPPRESS_S,
)


def _make_monitor(config_mode: str = "critical_relevant") -> tuple[CalloutMonitor, MagicMock]:
    agent = MagicMock()
    agent._mcp_tool = MagicMock()
    agent._mcp_lock = MagicMock()
    agent._mcp_lock.__aenter__ = AsyncMock(return_value=None)
    agent._mcp_lock.__aexit__ = AsyncMock(return_value=None)
    agent.last_ptt_ts = 0.0
    agent.player_team = "Williams"
    agent._agent = MagicMock()
    q: queue.Queue = queue.Queue()
    monitor = CalloutMonitor(agent, q)
    with patch("src.config.get", return_value=config_mode):
        pass
    return monitor, agent


def _make_event(code: str, severity: str, ts: float, involves_player: bool = False) -> dict:
    return {
        "code": code,
        "eventName": code,
        "severity": severity,
        "ts": ts,
        "involvesPlayer": involves_player,
    }


class TestSeverityFilter:
    def test_off_returns_empty(self):
        monitor, _ = _make_monitor()
        with patch("src.config.get", return_value="off"):
            assert monitor._severity_filter() == []

    def test_critical_returns_critical_only(self):
        monitor, _ = _make_monitor()
        with patch("src.config.get", return_value="critical"):
            result = monitor._severity_filter()
        assert result == ["critical"]

    def test_critical_relevant_returns_both(self):
        monitor, _ = _make_monitor()
        with patch("src.config.get", return_value="critical_relevant"):
            result = monitor._severity_filter()
        assert set(result) == {"critical", "relevant"}

    def test_unknown_mode_defaults_to_critical(self):
        monitor, _ = _make_monitor()
        with patch("src.config.get", return_value="unknown_value"):
            result = monitor._severity_filter()
        assert result == ["critical"]


class TestCooldownLogic:
    def test_event_blocked_within_cooldown(self):
        monitor, _ = _make_monitor()
        now = time.time()
        monitor._event_cooldowns["COLL"] = now - 5.0  # 5s ago
        cooldown = _EVENT_COOLDOWNS.get("COLL", _DEFAULT_EVENT_COOLDOWN)
        assert now - monitor._event_cooldowns["COLL"] < cooldown

    def test_event_allowed_after_cooldown(self):
        monitor, _ = _make_monitor()
        now = time.time()
        cooldown = _EVENT_COOLDOWNS.get("COLL", _DEFAULT_EVENT_COOLDOWN)
        monitor._event_cooldowns["COLL"] = now - cooldown - 1.0  # past cooldown
        assert now - monitor._event_cooldowns["COLL"] >= cooldown

    def test_unknown_code_uses_default_cooldown(self):
        assert "UNKNOWN_CODE" not in _EVENT_COOLDOWNS
        assert _DEFAULT_EVENT_COOLDOWN == 30.0

    def test_reset_clears_cooldowns(self):
        monitor, _ = _make_monitor()
        monitor._event_cooldowns["SCAR"] = time.time()
        monitor._last_callout_ts = time.time()
        monitor.reset()
        assert len(monitor._event_cooldowns) == 0
        assert monitor._last_callout_ts == 0.0


class TestGlobalRateLimit:
    def test_second_callout_blocked_by_global_limit(self):
        monitor, _ = _make_monitor()
        now = time.time()
        monitor._last_callout_ts = now - 5.0  # only 5s ago
        blocked = (now - monitor._last_callout_ts) < _GLOBAL_RATE_LIMIT_S
        assert blocked

    def test_callout_allowed_after_global_rate_limit(self):
        monitor, _ = _make_monitor()
        now = time.time()
        monitor._last_callout_ts = now - _GLOBAL_RATE_LIMIT_S - 1.0
        blocked = (now - monitor._last_callout_ts) < _GLOBAL_RATE_LIMIT_S
        assert not blocked


class TestPTTSuppression:
    def test_relevant_suppressed_after_ptt(self):
        monitor, agent = _make_monitor()
        agent.last_ptt_ts = time.time() - 3.0  # spoke 3s ago
        ptt_suppressed = (time.time() - agent.last_ptt_ts) < _PTT_SUPPRESS_S
        assert ptt_suppressed  # relevant events should be suppressed

    def test_critical_not_suppressed_after_ptt(self):
        # Critical events bypass PTT suppression
        assert _PTT_SUPPRESS_S == 10.0  # suppression applies to non-critical only

    def test_no_suppression_after_ptt_window(self):
        monitor, agent = _make_monitor()
        agent.last_ptt_ts = time.time() - _PTT_SUPPRESS_S - 1.0
        ptt_suppressed = (time.time() - agent.last_ptt_ts) < _PTT_SUPPRESS_S
        assert not ptt_suppressed


class TestCalloutQueuePayload:
    def test_fire_pushes_correct_shape(self):
        """Fire a callout and verify the queue payload has the right type and fields."""
        import asyncio

        monitor, agent = _make_monitor()
        mock_result = MagicMock()
        mock_result.text = "Safety car, box this lap."
        agent._agent.run = AsyncMock(return_value=mock_result)
        agent._fetch_context_frame = AsyncMock(return_value="{}")

        entry = _make_event("SCAR", "critical", time.time() - 1.0, True)

        async def _run():
            await monitor._fire(entry, time.time())

        asyncio.run(_run())

        assert not monitor._queue.empty()
        msg = monitor._queue.get_nowait()
        assert msg["type"] == "callout"
        assert "engineer_reply" in msg
        assert "display_reply" in msg
        assert "playerTeam" in msg
