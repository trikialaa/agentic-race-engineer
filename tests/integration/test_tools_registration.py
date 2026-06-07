"""
Integration test: MCP tool registration wiring.
Verifies that register_mcp_tools correctly binds all 6 tools through the
getattr(mcp_functions, name) path that the functions/ package split depends on.
No subprocess, no network.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from src.mcp.tools import TOOL_FUNCTIONS, register_mcp_tools
from tests.helpers import load_capture_to, load_markers

MARKERS = load_markers()


@pytest.fixture(scope="module")
def registered_mcp():
    """Build an MCP object with tools registered against a real fixture capture."""
    cap = load_capture_to(frame=MARKERS["start"])
    mcp = FastMCP("test")
    register_mcp_tools(mcp, cap)
    return mcp


def test_all_6_tools_registered(registered_mcp):
    tool_names = set(registered_mcp._tool_manager._tools.keys())
    for name in TOOL_FUNCTIONS:
        assert name in tool_names, f"Tool not registered: {name}"


def test_no_extra_tools_registered(registered_mcp):
    tool_names = set(registered_mcp._tool_manager._tools.keys())
    assert tool_names == set(TOOL_FUNCTIONS)


def test_tool_functions_resolve_from_package():
    """getattr(mcp_functions, name) must work for every tool name."""
    import src.mcp.functions as fns

    for name in TOOL_FUNCTIONS:
        fn = getattr(fns, name, None)
        assert fn is not None and callable(fn), f"mcp_functions.{name} not accessible"


def test_registered_tool_returns_dict():
    """Direct call through the function package returns a dict."""
    import src.mcp.functions as fns

    cap = load_capture_to(frame=MARKERS["start"])
    result = fns.get_context_frame(cap)
    assert isinstance(result, dict)
    assert "context" in result
