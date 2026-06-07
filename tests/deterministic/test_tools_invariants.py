"""
Semantic/structural invariant tests for all 6 MCP tools.
These survive intentional format tweaks; they check shape and correctness,
not exact values. This is the primary refactor-guard layer.
"""
from __future__ import annotations

import pytest

from tests.helpers import load_capture_to, load_markers

MARKERS = load_markers()


@pytest.fixture(scope="module")
def cap_start():
    return load_capture_to(frame=MARKERS["start"])


@pytest.fixture(scope="module")
def cap_green():
    return load_capture_to(frame=MARKERS["green_steady"])


@pytest.fixture(scope="module")
def cap_mid():
    return load_capture_to(frame=MARKERS["mid_strategy"])


@pytest.fixture(scope="module")
def cap_finish():
    return load_capture_to(frame=MARKERS["finish"])


# ── get_context_frame ─────────────────────────────────────────────────────────

class TestContextFrameInvariants:
    def test_has_context_key(self, cap_start):
        from src.mcp.functions.context_frame import get_context_frame
        result = get_context_frame(cap_start)
        assert "context" in result

    def test_session_fields_present(self, cap_start):
        from src.mcp.functions.context_frame import get_context_frame
        ctx = get_context_frame(cap_start)["context"]
        session = ctx["session"]
        assert session["type"] == "Race"
        assert session["track"] == "Catalunya"
        assert isinstance(session["lap"]["total"], int)

    def test_player_fields_present(self, cap_start):
        from src.mcp.functions.context_frame import get_context_frame
        ctx = get_context_frame(cap_start)["context"]
        player = ctx["player"]
        assert player["name"] == "SAINZ"
        assert player["team"] == "Williams"
        assert isinstance(player["position"]["current"], int)

    def test_tyre_info_present(self, cap_start):
        from src.mcp.functions.context_frame import get_context_frame
        ctx = get_context_frame(cap_start)["context"]
        tyre = ctx["player"]["car"]["tyre"]
        assert tyre["compound"] in ("soft", "medium", "hard", "inter", "wet")
        assert isinstance(tyre["ageLaps"], int)

    def test_weather_fields_present(self, cap_start):
        from src.mcp.functions.context_frame import get_context_frame
        ctx = get_context_frame(cap_start)["context"]
        weather = ctx["weather"]
        assert "type" in weather
        assert isinstance(weather["trackTempC"], (int, float))


# ── get_leaderboard ───────────────────────────────────────────────────────────

class TestLeaderboardInvariants:
    def test_returns_20_entries(self, cap_start):
        from src.mcp.functions.leaderboard import get_leaderboard
        result = get_leaderboard(cap_start)
        assert len(result["leaderboard"]) == 20

    def test_positions_are_unique_1_to_20(self, cap_start):
        from src.mcp.functions.leaderboard import get_leaderboard
        positions = [e["position"] for e in get_leaderboard(cap_start)["leaderboard"]]
        assert sorted(positions) == list(range(1, 21))

    def test_exactly_one_player(self, cap_start):
        from src.mcp.functions.leaderboard import get_leaderboard
        players = [e for e in get_leaderboard(cap_start)["leaderboard"] if e.get("isPlayer")]
        assert len(players) == 1
        assert players[0]["driver"] == "SAINZ"

    def test_all_entries_have_required_fields(self, cap_start):
        from src.mcp.functions.leaderboard import get_leaderboard
        required = {"position", "driver", "team", "gapToLeader", "visibleTyreCompound", "isPlayer"}
        for entry in get_leaderboard(cap_start)["leaderboard"]:
            assert required <= set(entry.keys()), f"Missing keys in: {entry}"

    def test_leader_gap_is_leader_string(self, cap_start):
        from src.mcp.functions.leaderboard import get_leaderboard
        lb = get_leaderboard(cap_start)["leaderboard"]
        leader = next(e for e in lb if e["position"] == 1)
        assert leader["gapToLeader"] == "LEADER"


# ── get_lap_times ─────────────────────────────────────────────────────────────

class TestLapTimesInvariants:
    def test_returns_list(self, cap_start):
        from src.mcp.functions.lap_times import get_lap_times
        result = get_lap_times(cap_start)
        assert isinstance(result.get("lapTimes"), list)

    def test_entries_have_required_fields(self, cap_start):
        from src.mcp.functions.lap_times import get_lap_times
        required = {"position", "driver", "carId", "mostRecent", "best"}
        for entry in get_lap_times(cap_start)["lapTimes"]:
            assert required <= set(entry.keys())

    def test_at_race_start_most_lap_times_unknown(self, cap_start):
        from src.mcp.functions.lap_times import get_lap_times
        times = [e["mostRecent"]["lap"] for e in get_lap_times(cap_start)["lapTimes"]]
        unknown_count = sum(1 for t in times if t == "unknown")
        assert unknown_count >= 1  # at least some cars have no lap time yet

    def test_at_green_steady_some_lap_times_known(self, cap_green):
        from src.mcp.functions.lap_times import get_lap_times
        times = [e["mostRecent"]["lap"] for e in get_lap_times(cap_green)["lapTimes"]]
        known = [t for t in times if t != "unknown"]
        # At the FTLP marker the fastest lap has just been set — at least that car's time is known
        assert len(known) >= 1, "Expected at least 1 car with a lap time at green_steady"


# ── get_weather_forecast ──────────────────────────────────────────────────────

class TestWeatherForecastInvariants:
    def test_has_current_and_forecast(self, cap_start):
        from src.mcp.functions.weather import get_weather_forecast
        result = get_weather_forecast(cap_start)
        assert "current" in result
        assert "forecast" in result

    def test_current_has_temperature_fields(self, cap_start):
        from src.mcp.functions.weather import get_weather_forecast
        current = get_weather_forecast(cap_start)["current"]
        assert isinstance(current["trackTempC"], (int, float))
        assert isinstance(current["airTempC"], (int, float))

    def test_forecast_has_3_horizons(self, cap_start):
        from src.mcp.functions.weather import get_weather_forecast
        forecast = get_weather_forecast(cap_start)["forecast"]
        assert len(forecast) == 3

    def test_forecast_horizons_increasing(self, cap_start):
        from src.mcp.functions.weather import get_weather_forecast
        offsets = [e["offsetMin"] for e in get_weather_forecast(cap_start)["forecast"]]
        assert offsets == sorted(offsets)
        assert offsets[0] == 0


# ── get_strategy ──────────────────────────────────────────────────────────────

class TestStrategyInvariants:
    def test_has_required_top_level_keys(self, cap_start):
        from src.mcp.functions.events import get_strategy
        result = get_strategy(cap_start)
        assert "pitWindow" in result
        assert "currentTyre" in result
        assert "availableSets" in result

    def test_available_sets_nonempty(self, cap_start):
        from src.mcp.functions.events import get_strategy
        sets = get_strategy(cap_start)["availableSets"]
        assert len(sets) >= 1

    def test_exactly_one_fitted_set(self, cap_start):
        from src.mcp.functions.events import get_strategy
        fitted = [s for s in get_strategy(cap_start)["availableSets"] if s.get("isFitted")]
        assert len(fitted) == 1

    def test_current_tyre_matches_fitted_compound(self, cap_start):
        from src.mcp.functions.events import get_strategy
        result = get_strategy(cap_start)
        current = result["currentTyre"]["compound"]
        fitted = next(s for s in result["availableSets"] if s.get("isFitted"))
        assert current == fitted["compound"]

    def test_set_compounds_are_valid(self, cap_start):
        from src.mcp.functions.events import get_strategy
        valid = {"soft", "medium", "hard", "inter", "wet", "unknown"}
        for s in get_strategy(cap_start)["availableSets"]:
            assert s["compound"] in valid


# ── get_recent_events ────────────────────────────────────────────────────────

class TestRecentEventsInvariants:
    def test_has_events_key(self, cap_green):
        from src.mcp.functions.events import get_recent_events
        result = get_recent_events(cap_green)
        assert "events" in result

    def test_events_list_nonempty_after_start(self, cap_green):
        from src.mcp.functions.events import get_recent_events
        events = get_recent_events(cap_green)["events"]
        assert len(events) >= 1

    def test_event_entries_have_required_fields(self, cap_green):
        from src.mcp.functions.events import get_recent_events
        required = {"code", "eventName", "severity", "involvesPlayer"}
        for entry in get_recent_events(cap_green)["events"]:
            assert required <= set(entry.keys())

    def test_severity_values_are_valid(self, cap_green):
        from src.mcp.functions.events import get_recent_events
        valid = {"critical", "relevant", "informational"}
        for entry in get_recent_events(cap_green)["events"]:
            assert entry["severity"] in valid

    def test_race_winner_event_at_finish(self, cap_finish):
        from src.mcp.functions.events import get_recent_events
        codes = {e["code"] for e in get_recent_events(cap_finish)["events"]}
        assert "RCWN" in codes or "CHQF" in codes, "Expected race winner or chequered flag event at finish"


# ── Cross-scenario consistency ────────────────────────────────────────────────

class TestCrossScenarioConsistency:
    def test_same_player_across_scenarios(self, cap_start, cap_green, cap_finish):
        from src.mcp.functions.context_frame import get_context_frame
        names = [
            get_context_frame(cap)["context"]["player"]["name"]
            for cap in (cap_start, cap_green, cap_finish)
        ]
        assert len(set(names)) == 1, f"Player name changed across scenarios: {names}"

    def test_leaderboard_driver_count_stable(self, cap_start, cap_green, cap_finish):
        from src.mcp.functions.leaderboard import get_leaderboard
        counts = [len(get_leaderboard(cap)["leaderboard"]) for cap in (cap_start, cap_green, cap_finish)]
        assert all(c == 20 for c in counts)
