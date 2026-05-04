from __future__ import annotations

from inspect import Signature, signature
from typing import Any, Callable, get_type_hints

from fastmcp import FastMCP

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp import functions as mcp_functions


TOOL_FUNCTIONS = [
    "get_context_frame",
    "get_leaderboard",
    "get_lap_times",
    "get_weather_forecast",
]

TOOL_DESCRIPTIONS = {
    "get_context_frame": (
        "Primary up-to-date race context for the current moment. "
        "Use first for most driver questions."
    ),
    "get_leaderboard": (
        "Race order and competitive context by driver. Includes gaps, tyre age, pit stops, "
        "penalties, and position change. Use to assess lost time, strategy differences, and traffic."
    ),
    "get_lap_times": (
        "Most recent and best lap/sector pace per driver. Use for pace comparison and where time is gained or lost."
    ),
    "get_weather_forecast": (
        "Current weather plus detailed forecast samples by offset. Use for rain timing and track evolution expectations."
    ),
}


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
        wrapper.__doc__ = TOOL_DESCRIPTIONS.get(tool_func.__name__, tool_func.__doc__)
        mcp.tool(
            name=tool_func.__name__,
            description=TOOL_DESCRIPTIONS.get(tool_func.__name__),
        )(wrapper)
    for name in TOOL_FUNCTIONS:
        func = getattr(mcp_functions, name)
        bind(func)
