from __future__ import annotations

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
        "and penalties. Use this when the driver asks about the wider field, cars outside their immediate "
        "vicinity, or when comparing strategies across multiple drivers. "
        "Prefer get_context_frame for questions about the two cars directly around the player."
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
        "Pit stop strategy data: optimal pit window (ideal and latest lap, laps remaining until window), "
        "estimated rejoin position, current tyre compound and age, and all available tyre sets with "
        "remaining wear and pace delta. Use for pit timing, undercut/overcut analysis, and tyre choice. "
        "get_context_frame has the current tyre compound and age; call this only when the driver "
        "is asking about when to pit or which tyre to fit."
    ),
    "get_recent_events": (
        "Chronological list of classified race events: safety car, red flag, collisions, penalties, "
        "overtakes, DRS zones, fastest laps, retirements, and race winner. "
        "Each entry includes severity (critical/relevant/informational) and whether it involves the player. "
        "Use when the driver asks what happened, whether a penalty was issued, or to confirm an incident."
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
        mcp.tool(
            name=tool_func.__name__,
            description=TOOL_DESCRIPTIONS.get(tool_func.__name__),
        )(wrapper)

    for name in TOOL_FUNCTIONS:
        func = getattr(mcp_functions, name)
        bind(func)
