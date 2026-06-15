from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from inspect import Signature, signature
from typing import Any, get_type_hints

from fastmcp import FastMCP

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp import functions as mcp_functions

TOOL_FUNCTIONS = [
    "get_context_frame",
    "get_leaderboard",
    "get_lap_times",
    "get_weather_forecast",
    "get_strategy",
    "get_recent_events",
    "get_race_report",
]

TOOL_DESCRIPTIONS = {
    "get_context_frame": (
        "Primary snapshot of the current race moment: player position, gaps to cars ahead/behind, "
        "tyre compound and age, fuel load, damage, DRS, current lap, session phase, and recent events. "
        "Call this first for any question about the player's own car or immediate race situation. "
        "Do NOT call get_leaderboard or get_lap_times just to answer a simple gap or tyre question — "
        "get_context_frame already contains that data."
    ),
    "get_leaderboard": (
        "Full field view: every car's race position, gap to leader, tyre compound and age, pit stop count, "
        "and penalties. Call this whenever the driver asks about any specific driver who is NOT shown as "
        "frontDriver or backDriver in the context frame — including the race leader, the driver behind them, "
        "or any named driver you cannot locate in the immediate gap data. "
        "Also use for comparing strategies across multiple drivers or questions about the wider field."
    ),
    "get_lap_times": (
        "Lap-by-lap and sector-by-sector pace for all drivers. Use for questions about who is fastest, "
        "where time is being lost or gained on track, or whether a specific driver is on a push lap. "
        "Do not use this to answer gap or position questions — use get_context_frame or get_leaderboard instead."
    ),
    "get_weather_forecast": (
        "Current track and air conditions plus a time-series forecast of weather changes. "
        "Use for any question about rain timing, when to switch to wets/inters, or how the track "
        "is expected to evolve. Not needed for dry-weather strategy calls."
    ),
    "get_strategy": (
        "Pit stop strategy data: lapsRemaining in the race, optimal pit window (ideal and latest lap, "
        "laps until window), estimated rejoin position, current tyre compound/age/wear, and all available "
        "tyre sets with remaining wear and pace delta (lapDeltaMs — milliseconds slower than current tyre, "
        "lower = faster). "
        "ALWAYS call this when the driver asks which tyre to fit or for any tyre compound recommendation — "
        "lapDeltaMs is the only reliable way to compare compounds, but ALSO cross-check lapsRemaining: "
        "a faster compound that cannot survive the remaining stint is the wrong choice. "
        "Also call for pit timing, undercut/overcut analysis, and rejoin position."
    ),
    "get_recent_events": (
        "Chronological list of classified race events: safety car, red flag, collisions, penalties, "
        "overtakes, DRS zones, fastest laps, retirements, and race winner. "
        "Each entry includes severity (critical/relevant/informational) and whether it involves the player. "
        "Use when the driver asks what happened, whether a penalty was issued, or to confirm an incident."
    ),
    "get_race_report": (
        "Post-race summary: final classifications with position, grid position, position change, "
        "best lap time, pit stop count, tyre stints, and notable events (fastest lap, penalties, retirements). "
        "Only useful after the race ends. Returns available=false if final classification data is not yet received."
    ),
}


def register_mcp_tools(mcp: FastMCP, capture: F1TelemetryCapture) -> None:
    """Register telemetry tools with the FastMCP server."""

    def bind(tool_func: Callable):
        base_sig = signature(tool_func)
        params = list(base_sig.parameters.values())[1:]
        type_hints = get_type_hints(tool_func, globalns=tool_func.__globals__)
        tool_params = [
            param.replace(annotation=type_hints.get(param.name, param.annotation))
            for param in params
        ]
        return_annotation = type_hints.get("return", base_sig.return_annotation)
        tool_signature = Signature(parameters=tool_params, return_annotation=return_annotation)
        annotations: dict[str, Any] = {}
        for param in tool_params:
            if param.annotation is not Signature.empty:
                annotations[param.name] = param.annotation
        if return_annotation is not Signature.empty:
            annotations["return"] = return_annotation

        param_defs = ", ".join(str(param) for param in tool_params)
        param_names = ", ".join(param.name for param in tool_params)
        func_globals = dict(tool_func.__globals__)
        func_globals.update({"tool_func": tool_func, "capture": capture})
        func_code = f"""
def generated_tool({param_defs}):
    return tool_func(capture{", " if param_names else ""}{param_names})
"""
        exec_globals: dict[str, Any] = {}
        exec(func_code, func_globals, exec_globals)
        wrapper = exec_globals["generated_tool"]
        wrapper.__name__ = tool_func.__name__
        wrapper.__signature__ = tool_signature
        wrapper.__annotations__ = annotations
        wrapper.__doc__ = TOOL_DESCRIPTIONS.get(tool_func.__name__, tool_func.__doc__)
        tool_log_path = os.getenv("F1_MCP_TOOL_LOG")
        if tool_log_path:
            inner = wrapper
            tool_name = tool_func.__name__

            def _logged(*args, _inner=inner, _name=tool_name, _log=tool_log_path, **kwargs):
                with open(_log, "a") as _f:
                    _f.write(json.dumps({"tool": _name, "ts": time.time()}) + "\n")
                return _inner(*args, **kwargs)

            _logged.__name__ = wrapper.__name__
            _logged.__signature__ = tool_signature
            _logged.__annotations__ = annotations
            _logged.__doc__ = wrapper.__doc__
            wrapper = _logged

        mcp.tool(
            name=tool_func.__name__,
            description=TOOL_DESCRIPTIONS.get(tool_func.__name__),
        )(wrapper)

    for name in TOOL_FUNCTIONS:
        func = getattr(mcp_functions, name)
        bind(func)
