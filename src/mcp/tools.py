from __future__ import annotations

from inspect import Signature, signature
from typing import Any, Callable, get_type_hints

from fastmcp import FastMCP

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp import functions as mcp_functions


TOOL_FUNCTIONS = [
    "get_session_info",
    "get_current_weather",
    "get_weather_forecast",
    "get_total_laps",
    "get_current_track",
    "get_safety_car_status",
    "get_pitstop_window_recommendation",
    "get_pitstop_rejoin_position",
    "get_race_standings",
    "get_player_telemetry",
    "get_recent_events",
    "get_current_lap",
    "get_num_remaining_laps",
    "get_penalties",
    "get_penalties_by_player",
    "get_teammate_position",
    "get_player_position_by_name",
    "get_all_grid_positions",
    "get_safety_car_delta",
    "get_player_name_by_position",
    "get_fastest_lap_data",
    "get_penalities",
    "get_penalities_by_driver_name",
    "get_drs_status",
    "get_driver_by_position",
    "get_driver_by_name",
    "get_top_drivers",
    "get_race_summary",
    "get_capture_stats",
    "get_current_position",
    "get_gap_to_driver_by_name",
    "get_gap_to_driver_by_position",
    "get_gap_to_driver_in_front",
    "get_gap_to_driver_in_back",
    "get_fuel_status",
    "get_ers_status",
    "get_tyres_status",
    "get_damage_status",
    "get_car_telemetry_history",
    "get_car_status_changes",
    "get_car_damage_events",
    "get_car_lap_history",
    "get_session_changes",
    "get_session_forecast",
    "get_safety_periods",
]


def register_mcp_tools(mcp: FastMCP, capture: F1TelemetryCapture) -> None:
    """Register telemetry tools with the FastMCP server."""

    def bind(tool_func: Callable):
        base_sig = signature(tool_func)
        params = list(base_sig.parameters.values())[1:]
        type_hints = get_type_hints(tool_func, globalns=tool_func.__globals__)
        tool_params = [
            param.replace(
                annotation=type_hints.get(param.name, param.annotation)
            )
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
    return tool_func(capture{', ' if param_names else ''}{param_names})
"""
        exec_globals: dict[str, Any] = {}
        exec(func_code, func_globals, exec_globals)
        wrapper = exec_globals["generated_tool"]
        wrapper.__name__ = tool_func.__name__
        wrapper.__signature__ = tool_signature
        wrapper.__annotations__ = annotations
        mcp.tool()(wrapper)
    for name in TOOL_FUNCTIONS:
        func = getattr(mcp_functions, name)
        bind(func)
