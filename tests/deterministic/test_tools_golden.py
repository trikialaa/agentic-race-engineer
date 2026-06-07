"""
Golden-snapshot tests for the 4 pure-read MCP tools.
Each test loads the fixture up to a known marker frame, calls the tool,
masks wall-clock fields, and compares against a committed golden JSON.

To regenerate goldens after intentional format changes:
  python tests/fixtures/build_fixture.py --skip-parity --update-golden
"""

from __future__ import annotations

import pytest

from tests.helpers import load_capture_to, load_golden, load_markers, mask

MARKERS = load_markers()

# (tool_name, scenario) pairs we assert golden-exact output for.
# get_lap_times and get_recent_events are excluded (stateful/timing-sensitive —
# covered by invariant tests instead).
CASES = [
    (tool, scenario)
    for tool in ("get_context_frame", "get_leaderboard", "get_weather_forecast", "get_strategy")
    for scenario in ("start", "green_steady", "finish")
]


@pytest.fixture(scope="module")
def captures_by_scenario():
    """Load one capture per scenario (expensive: session-scoped so it runs once)."""
    caps = {}
    for scenario in ("start", "green_steady", "finish"):
        caps[scenario] = load_capture_to(frame=MARKERS[scenario])
    return caps


@pytest.mark.parametrize("tool,scenario", CASES, ids=lambda x: x)
def test_golden(tool, scenario, captures_by_scenario):
    import src.mcp.functions as fns

    cap = captures_by_scenario[scenario]
    fn = getattr(fns, tool)
    result = fn(cap)
    actual = mask(result)
    expected = load_golden(tool, scenario)
    assert actual == expected, (
        f"{tool} @ {scenario}: output differs from golden. "
        "If change is intentional, run: python tests/fixtures/build_fixture.py --skip-parity --update-golden"
    )
