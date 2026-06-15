"""Per-event callout message builders.

Each builder receives a classified event dict, the RaceEngineerAgent, and the optional
CalloutMonitor (for stateful caches like last-seen damage levels), and returns either a
fully formed [CALLOUT] instruction string or None to suppress the callout silently.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.voice_pipeline.agent import RaceEngineerAgent
    from src.voice_pipeline.callouts import CalloutMonitor

logger = logging.getLogger(__name__)

# Damage levels ordered by increasing severity
_DAMAGE_ORDER: dict[str, int] = {"undamaged": 0, "low": 1, "medium": 2, "high": 3}
# Minimum level (inclusive) at which a player collision warrants a callout
_DAMAGE_FIRE_THRESHOLD = 2  # "medium"

_PART_DISPLAY = {
    "frontWing": "front wing",
    "rearWing": "rear wing",
    "floor": "floor",
    "diffuser": "diffuser",
}


async def _call_mcp(agent: RaceEngineerAgent, tool_name: str, timeout: float = 2.0) -> dict:
    """Call an MCP tool and return parsed JSON dict, or empty dict on error."""
    if agent._mcp_tool is None:
        return {}
    try:
        async with agent._mcp_lock:
            raw = await asyncio.wait_for(agent._mcp_tool.call_tool(tool_name), timeout=timeout)
        if isinstance(raw, list) and raw:
            text = raw[0].text
            return json.loads(text) if isinstance(text, str) else {}
    except Exception as exc:
        logger.warning("MCP %s failed in callout builder: %s", tool_name, exc)
    return {}


def _extract_damage_levels(ctx: dict) -> dict[str, str]:
    try:
        return dict(ctx["context"]["player"]["car"]["damageByPart"])
    except (KeyError, TypeError):
        return {}


# ── Per-event builders ────────────────────────────────────────────────────────


async def _build_rdfl(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    return "[CALLOUT] Red flag. Radio the driver."


async def _build_chqf(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    ctx = await _call_mcp(agent, "get_context_frame")
    leaderboard_data = await _call_mcp(agent, "get_leaderboard")

    position_block = ctx.get("context", {}).get("player", {}).get("position", {})
    current = position_block.get("current")
    start = position_block.get("start")

    pos_facts: list[str] = []
    diff: int | None = None
    if isinstance(current, int):
        pos_facts.append(f"P{current}")
    if isinstance(start, int):
        pos_facts.append(f"started P{start}")
    if isinstance(current, int) and isinstance(start, int):
        diff = start - current
        if diff > 0:
            pos_facts.append(f"gained {diff} place{'s' if diff != 1 else ''}")
        elif diff < 0:
            pos_facts.append(f"lost {abs(diff)} place{'s' if abs(diff) != 1 else ''}")

    player_row = next(
        (r for r in (leaderboard_data.get("leaderboard") or []) if r.get("isPlayer")),
        None,
    )
    penalty_parts: list[str] = []
    if player_row:
        penalty_parts = player_row.get("unservedPenalties") or []

    if diff is None:
        tone = ""
    elif diff > 0:
        tone = "Be encouraging — the result was positive."
    elif diff < 0:
        tone = "Be measured — acknowledge the tough result, say we'll review."
    else:
        tone = "Be neutral — the position was held."

    facts = ", ".join(pos_facts) if pos_facts else "race complete"
    penalty_str = f" Unserved penalties: {'; '.join(penalty_parts)}." if penalty_parts else ""
    return f"[CALLOUT] Chequered flag. {facts}.{penalty_str} {tone} Radio the driver."


async def _build_coll(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    involves_player = entry.get("involvesPlayer", False)
    if not involves_player:
        return "[CALLOUT] Collision nearby. Radio the driver."

    ctx = await _call_mcp(agent, "get_context_frame")
    current_levels = _extract_damage_levels(ctx)
    cached_levels: dict[str, str] = monitor._last_damage_levels if monitor is not None else {}

    damaged_parts: list[str] = []
    serious = False
    for part, level in current_levels.items():
        old_order = _DAMAGE_ORDER.get(cached_levels.get(part, "undamaged"), 0)
        new_order = _DAMAGE_ORDER.get(level, 0)
        if new_order > old_order and new_order >= _DAMAGE_FIRE_THRESHOLD:
            damaged_parts.append(part)
            if new_order >= _DAMAGE_ORDER["high"]:
                serious = True

    if monitor is not None:
        monitor._last_damage_levels = dict(current_levels)

    if not damaged_parts:
        return None  # Harmless tap — suppress

    part_str = ", ".join(_PART_DISPLAY.get(p, p) for p in damaged_parts)
    advice = "box this lap to assess" if serious else "keep an eye on it"
    return f"[CALLOUT] Contact — {part_str} damage, {advice}. One sentence."


async def _build_rtmt(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    involves_player = entry.get("involvesPlayer", False)
    details = entry.get("details", {}) or {}
    reason = details.get("reasonName", "retirement")

    if involves_player:
        return f"[CALLOUT] Retirement, {reason}. Radio the driver."
    return f"[CALLOUT] Rival retired, {reason}. Radio the driver."


async def _build_yelw(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    details = entry.get("details", {}) or {}
    immediate = details.get("immediateRisk", False)
    if immediate:
        return "[CALLOUT] Yellow flag, immediate risk ahead. Radio the driver."
    return "[CALLOUT] Yellow flag. Radio the driver."


async def _build_scar(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    details = entry.get("details", {}) or {}
    sc_type = details.get("safetyCarTypeName", "Safety Car")
    event_type = details.get("eventTypeName", "Deployed")

    if "Formation" in sc_type:
        return None  # Formation lap SC — not actionable

    if event_type in ("Returning", "Returned", "Resume Race"):
        return (
            f"[CALLOUT] {sc_type} {event_type.lower()}. "
            "Alert the driver to prepare to race. One sentence."
        )

    if "Virtual" in sc_type:
        return (
            "[CALLOUT] Virtual safety car. "
            "Tell the driver to hold the delta and not close up. One sentence."
        )

    # Full safety car deployed
    return "[CALLOUT] Safety car. Instruct the driver to box this lap. One sentence."


async def _build_pena(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    details = entry.get("details", {}) or {}
    involves_player = entry.get("involvesPlayer", False)
    penalty_type = details.get("penaltyTypeName", "Penalty")
    penalty_time = details.get("time")

    time_str = f" {penalty_time}s" if isinstance(penalty_time, int) and penalty_time > 0 else ""
    if involves_player:
        return f"[CALLOUT] Penalty issued to you — {penalty_type}{time_str}. Radio the driver."
    return f"[CALLOUT] Rival penalty — {penalty_type}{time_str}. Radio the driver."


async def _build_drse(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    return "[CALLOUT] DRS enabled. Radio the driver."


async def _build_drsd(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    details = entry.get("details", {}) or {}
    reason = details.get("reasonName", "")
    reason_str = f", {reason}" if reason else ""
    return f"[CALLOUT] DRS disabled{reason_str}. Radio the driver."


async def _build_ftlp(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    details = entry.get("details", {}) or {}
    involves_player = entry.get("involvesPlayer", False)
    lap_time = details.get("lapTimeFormatted", "")
    time_str = f" — {lap_time}" if lap_time else ""
    if involves_player:
        return f"[CALLOUT] Player set fastest lap{time_str}. Radio the driver."
    return f"[CALLOUT] Rival fastest lap{time_str}. Radio the driver."


async def _build_ovtk(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    details = entry.get("details", {}) or {}
    overtaking_idx = details.get("overtakingVehicleIdx")
    being_overtaken_idx = details.get("beingOvertakenVehicleIdx")

    # Use pit status stamped at event-emit time (not live) to avoid racing the pit exit.
    if entry.get("playerPitStatus", "none") != "none":
        return None  # Position changes while pitting are not racing overtakes

    ctx = await _call_mcp(agent, "get_context_frame")
    player_block = ctx.get("context", {}).get("player", {}) or {}
    player_idx = player_block.get("id")
    current_pos = player_block.get("position", {}).get("current")

    player_gained = isinstance(player_idx, int) and overtaking_idx == player_idx
    player_lost = isinstance(player_idx, int) and being_overtaken_idx == player_idx

    if not player_gained and not player_lost:
        # Involves player index but neither slot matches — suppress to avoid mystery callout
        return None

    rival_idx = being_overtaken_idx if player_gained else overtaking_idx
    rival_name: str | None = None
    if isinstance(rival_idx, int):
        lb = await _call_mcp(agent, "get_leaderboard")
        for row in lb.get("leaderboard") or []:
            if row.get("carIndex") == rival_idx:
                rival_name = row.get("driver")
                break

    pos_str = f" now P{current_pos}" if isinstance(current_pos, int) else ""

    if player_gained:
        rival_str = f" past {rival_name}" if rival_name else ""
        return f"[CALLOUT] Player gained a place{rival_str},{pos_str}. Radio the driver."
    else:
        rival_str = f" to {rival_name}" if rival_name else ""
        return f"[CALLOUT] Player lost a place{rival_str},{pos_str}. Radio the driver."


async def _build_llap(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    ctx = await _call_mcp(agent, "get_context_frame")
    player = ctx.get("context", {}).get("player", {}) or {}
    pos = player.get("position", {}).get("current")
    total = player.get("position", {}).get("total")
    gap_front = player.get("gap", {}).get("frontS")
    gap_back = player.get("gap", {}).get("backS")
    front_driver = (player.get("gap", {}).get("frontDriver") or {}).get("name")
    back_driver = (player.get("gap", {}).get("backDriver") or {}).get("name")

    facts: list[str] = []
    if isinstance(pos, int):
        facts.append(f"P{pos}" + (f" of {total}" if isinstance(total, int) else ""))
    if isinstance(gap_front, (int, float)) and front_driver:
        facts.append(f"{gap_front:.1f}s to {front_driver} ahead")
    if isinstance(gap_back, (int, float)) and back_driver:
        facts.append(f"{gap_back:.1f}s to {back_driver} behind")

    fact_str = ", ".join(facts) if facts else "final lap"
    return f"[CALLOUT] Final lap. {fact_str}. Radio the driver."


async def _build_generic(
    entry: dict, agent: RaceEngineerAgent, monitor: CalloutMonitor | None
) -> str | None:
    code = entry.get("code", "")
    event_name = entry.get("eventName", code)
    involves_player = entry.get("involvesPlayer", False)
    details = entry.get("details", {}) or {}
    detail_parts: list[str] = []
    if involves_player:
        detail_parts.append("involving you")
    if penalty_type := details.get("penaltyTypeName"):
        detail_parts.append(str(penalty_type))
    if penalty_time := details.get("time"):
        if isinstance(penalty_time, int) and penalty_time > 0:
            detail_parts.append(f"{penalty_time}s")
    detail_str = f" ({', '.join(detail_parts)})" if detail_parts else ""
    return f"[CALLOUT] {event_name}{detail_str}. Radio the driver."


_BUILDERS = {
    "RDFL": _build_rdfl,
    "CHQF": _build_chqf,
    "COLL": _build_coll,
    "RTMT": _build_rtmt,
    "YELW": _build_yelw,
    "SCAR": _build_scar,
    "PENA": _build_pena,
    "DRSE": _build_drse,
    "DRSD": _build_drsd,
    "FTLP": _build_ftlp,
    "OVTK": _build_ovtk,
    "LLAP": _build_llap,
}


async def build_callout_message(
    entry: dict,
    agent: RaceEngineerAgent,
    monitor: CalloutMonitor | None = None,
) -> str | None:
    """Return a [CALLOUT] instruction string for the event, or None to suppress."""
    code = entry.get("code", "")
    builder = _BUILDERS.get(code, _build_generic)
    try:
        return await builder(entry, agent, monitor)
    except Exception as exc:
        logger.warning("Callout builder for %s failed (%s), falling back to generic", code, exc)
        try:
            return await _build_generic(entry, agent, monitor)
        except Exception:
            return None
