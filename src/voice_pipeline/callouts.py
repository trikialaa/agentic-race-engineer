from __future__ import annotations

import asyncio
import json
import logging
import queue
import time
from typing import TYPE_CHECKING

from src.voice_pipeline.tts_utils import sanitize_for_tts

if TYPE_CHECKING:
    from src.voice_pipeline.agent import RaceEngineerAgent

logger = logging.getLogger(__name__)

# Per-event-code callout cooldowns (seconds)
_EVENT_COOLDOWNS: dict[str, float] = {
    "SCAR": 90.0,  # Safety car deployed
    "RDFL": 120.0,  # Red flag
    "COLL": 45.0,  # Collision
    "PENA": 30.0,  # Penalty issued
    "OVTK": 30.0,  # Overtake
    "DRSE": 30.0,  # DRS enabled
    "DRSD": 30.0,  # DRS disabled
    "FTLP": 60.0,  # Fastest lap set
    "RCWN": 60.0,  # Race winner declared
}
_DEFAULT_EVENT_COOLDOWN = 30.0
_GLOBAL_RATE_LIMIT_S = 20.0  # minimum gap between any two callout messages
_PTT_SUPPRESS_S = 10.0  # suppress relevant (non-critical) callouts after user speaks


class CalloutMonitor:
    """Monitors classified race events and fires engineer callouts autonomously."""

    def __init__(self, agent: RaceEngineerAgent, q: queue.Queue) -> None:
        self._agent = agent
        self._queue = q
        self._event_last_checked_ts: float = time.time()
        self._event_cooldowns: dict[str, float] = {}
        self._last_callout_ts: float = 0.0

    def reset(self) -> None:
        self._event_cooldowns.clear()
        self._last_callout_ts = 0.0
        self._event_last_checked_ts = time.time()

    def _severity_filter(self) -> list[str]:
        from src import config as _app_config

        mode = _app_config.get("engineerCallouts", _app_config.get("proactiveEvents", "critical"))
        if mode == "off":
            return []
        if mode == "critical_relevant":
            return ["critical", "relevant"]
        return ["critical"]

    async def check(self) -> None:
        agent = self._agent
        if agent._mcp_tool is None:
            return
        severity_filter = self._severity_filter()
        if not severity_filter:
            return

        now = time.time()
        since_ts = self._event_last_checked_ts

        try:
            async with agent._mcp_lock:
                raw = await asyncio.wait_for(
                    agent._mcp_tool.call_tool("get_recent_events"),
                    timeout=2.0,
                )
            self._event_last_checked_ts = now
        except Exception as exc:
            logger.warning("get_recent_events failed: %s", exc)
            return

        if isinstance(raw, list) and raw:
            data_str = raw[0].text
        else:
            return

        try:
            data = json.loads(data_str) if isinstance(data_str, str) else data_str
            events = data.get("events", [])
        except Exception:
            return

        severity_set = set(severity_filter)
        ptt_suppressed = (now - agent.last_ptt_ts) < _PTT_SUPPRESS_S

        for entry in events:
            if not isinstance(entry, dict):
                continue
            entry_ts = entry.get("ts", 0.0)
            if not isinstance(entry_ts, float) or entry_ts <= since_ts:
                continue
            severity = entry.get("severity", "")
            if severity not in severity_set:
                continue
            if ptt_suppressed and severity != "critical":
                continue
            code = entry.get("code", "")
            cooldown = _EVENT_COOLDOWNS.get(code, _DEFAULT_EVENT_COOLDOWN)
            if now - self._event_cooldowns.get(code, 0.0) < cooldown:
                continue
            if now - self._last_callout_ts < _GLOBAL_RATE_LIMIT_S:
                continue

            await self._fire(entry, now)
            break  # one callout per poll cycle

    async def _fire(self, entry: dict, now: float) -> None:
        agent = self._agent
        assert agent._agent is not None
        code = entry.get("code", "")
        event_name = entry.get("eventName", code)
        details = entry.get("details", {}) or {}
        involves_player = entry.get("involvesPlayer", False)

        # Update timestamps before the LLM call to prevent concurrent fires
        self._event_cooldowns[code] = now
        self._last_callout_ts = now

        detail_parts: list[str] = []
        if involves_player:
            detail_parts.append("involving you")
        if penalty_type := details.get("penaltyTypeName"):
            detail_parts.append(str(penalty_type))
        if penalty_time := details.get("time"):
            if isinstance(penalty_time, int) and penalty_time > 0:
                detail_parts.append(f"{penalty_time}s")
        detail_str = f" ({', '.join(detail_parts)})" if detail_parts else ""

        callout_msg = (
            f"[CALLOUT] {event_name}{detail_str}. "
            "Alert the driver with one short engineer radio call."
        )

        try:
            snapshot = await agent._fetch_context_frame()
        except Exception as exc:
            logger.warning("Callout context frame failed: %s", exc)
            snapshot = "{}"

        request_text = f"Context frame, latest telemetry snapshot:\n{snapshot}\n\n{callout_msg}"

        run_kwargs = {"tools": agent._mcp_tool} if agent._mcp_tool is not None else {}
        try:
            async with agent._mcp_lock:
                result = await asyncio.wait_for(
                    agent._agent.run(request_text, client_kwargs={"store": False}, **run_kwargs),
                    timeout=7.0,
                )
        except TimeoutError:
            logger.warning("Callout agent.run timed out for event %s", code)
            return
        except Exception as exc:
            logger.warning("Callout agent.run failed for event %s: %s", code, exc)
            return

        reply_raw = getattr(result, "text", None)
        if not isinstance(reply_raw, str) or not reply_raw.strip():
            return

        self._queue.put(
            {
                "type": "callout",
                "engineer_reply": sanitize_for_tts(reply_raw),
                "display_reply": reply_raw,
                "playerTeam": agent.player_team or "",
            }
        )
        logger.info("Callout fired: %s → %s", event_name, reply_raw[:80])
