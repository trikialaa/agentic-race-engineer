import asyncio
import os
import sys
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

try:
    from pydantic import BaseModel  # type: ignore
except Exception:
    BaseModel = None  # pragma: no cover - fallback if pydantic missing


class F1TelemetryClient:
    def __init__(self, script_path: str | os.PathLike[str] = "src/mcp/server.py"):
        full_path = os.path.abspath(script_path)
        transport = StdioTransport(
            command=sys.executable,
            args=[full_path],
            cwd=os.path.dirname(full_path),
            env=os.environ.copy(),
        )
        self.client = Client(transport=transport)

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.__aexit__(exc_type, exc, tb)

    async def _call_tool(self, tool: str, params=None):
        return await self.client.call_tool(tool, params or {})

    async def a_get_session_info(self):
        return await self.client.call_tool("get_session_info", {})

    async def a_get_race_standings(self, limit=22):
        return await self.client.call_tool("get_race_standings", {"limit": limit})

    async def a_get_race_summary(self):
        return await self.client.call_tool("get_race_summary", {})

    async def a_get_player_telemetry(self):
        return await self.client.call_tool("get_player_telemetry", {})

    async def a_get_recent_events(self, limit=5):
        return await self.client.call_tool("get_recent_events", {"limit": limit})

    async def a_get_driver_by_position(self, position):
        return await self.client.call_tool("get_driver_by_position", {"position": position})

    async def a_get_driver_by_name(self, name):
        return await self.client.call_tool("get_driver_by_name", {"name": name})

    async def a_get_top_drivers(self, count=5):
        return await self.client.call_tool("get_top_drivers", {"count": count})

    async def a_get_car_telemetry_history(self, car_index, limit=50):
        return await self.client.call_tool("get_car_telemetry_history", {"car_index": car_index, "limit": limit})

    async def a_get_car_status_changes(self, car_index, limit=50):
        return await self.client.call_tool("get_car_status_changes", {"car_index": car_index, "limit": limit})

    async def a_get_car_damage_events(self, car_index, limit=50):
        return await self.client.call_tool("get_car_damage_events", {"car_index": car_index, "limit": limit})

    async def a_get_car_lap_history(self, car_index, limit=50):
        return await self.client.call_tool("get_car_lap_history", {"car_index": car_index, "limit": limit})

    async def a_get_session_changes(self, limit=50):
        return await self.client.call_tool("get_session_changes", {"limit": limit})

    async def a_get_session_forecast(self, limit=10):
        return await self.client.call_tool("get_session_forecast", {"limit": limit})

    async def a_get_safety_periods(self):
        return await self.client.call_tool("get_safety_periods", {})

    async def a_get_current_weather(self):
        return await self._call_tool("get_current_weather")

    async def a_get_weather_forecast(self):
        return await self._call_tool("get_weather_forecast")

    async def a_get_total_laps(self):
        return await self._call_tool("get_total_laps")

    async def a_get_current_track(self):
        return await self._call_tool("get_current_track")

    async def a_get_safety_car_status(self):
        return await self._call_tool("get_safety_car_status")

    async def a_get_pitstop_window_recommendation(self):
        return await self._call_tool("get_pitstop_window_recommendation")

    async def a_get_pitstop_rejoin_position(self):
        return await self._call_tool("get_pitstop_rejoin_position")

    async def a_get_current_lap(self):
        return await self._call_tool("get_current_lap")

    async def a_get_num_remaining_laps(self):
        return await self._call_tool("get_num_remaining_laps")

    async def a_get_penalties(self):
        return await self._call_tool("get_penalties")

    async def a_get_penalties_by_player(self, name):
        return await self._call_tool("get_penalties_by_player", {"name": name})

    async def a_get_teammate_position(self):
        return await self._call_tool("get_teammate_position")

    async def a_get_player_position_by_name(self, name):
        return await self._call_tool("get_player_position_by_name", {"name": name})

    async def a_get_all_grid_positions(self):
        return await self._call_tool("get_all_grid_positions")

    async def a_get_safety_car_delta(self):
        return await self._call_tool("get_safety_car_delta")

    async def a_get_player_name_by_position(self, position):
        return await self._call_tool("get_player_name_by_position", {"position": position})

    async def a_get_fastest_lap_data(self):
        return await self._call_tool("get_fastest_lap_data")

    async def a_get_penalities(self):
        return await self._call_tool("get_penalities")

    async def a_get_penalities_by_driver_name(self, name):
        return await self._call_tool("get_penalities_by_driver_name", {"name": name})

    async def a_get_drs_status(self):
        return await self._call_tool("get_drs_status")

    async def a_get_capture_stats(self):
        return await self._call_tool("get_capture_stats")

    async def a_get_current_position(self):
        return await self._call_tool("get_current_position")

    async def a_get_gap_to_driver_by_name(self, name):
        return await self._call_tool("get_gap_to_driver_by_name", {"name": name})

    async def a_get_gap_to_driver_by_position(self, position):
        return await self._call_tool("get_gap_to_driver_by_position", {"position": position})

    async def a_get_gap_to_driver_in_front(self):
        return await self._call_tool("get_gap_to_driver_in_front")

    async def a_get_gap_to_driver_in_back(self):
        return await self._call_tool("get_gap_to_driver_in_back")

    async def a_get_fuel_status(self):
        return await self._call_tool("get_fuel_status")

    async def a_get_ers_status(self):
        return await self._call_tool("get_ers_status")

    async def a_get_tyres_status(self):
        return await self._call_tool("get_tyres_status")

    async def a_get_damage_status(self):
        return await self._call_tool("get_damage_status")

def _print(tool: str, result):
    """Nicely display tool results from FastMCP CallToolResult."""
    try:
        import json
        def to_plain(obj: Any):
            if isinstance(obj, dict):
                return {k: to_plain(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [to_plain(v) for v in obj]
            if BaseModel and isinstance(obj, BaseModel):
                return to_plain(obj.model_dump())
            if hasattr(obj, "__root__"):
                try:
                    return to_plain(obj.__root__)
                except Exception:
                    pass
            if hasattr(obj, "model_dump"):
                return to_plain(obj.model_dump())
            if hasattr(obj, "dict"):
                return to_plain(obj.dict())
            if isinstance(obj, bytes):
                try:
                    return obj.decode("utf-8", "ignore")
                except Exception:
                    return obj.hex()
            return obj

        payload = result.data if hasattr(result, "data") else result
        payload = to_plain(payload)
        print(f"\n--- {tool} ---")
        print(json.dumps(payload, indent=2))
    except Exception as exc:
        print(f"\n--- {tool} (could not format: {exc}) ---")
        print(result)


async def main():
    async with F1TelemetryClient() as client:
        call_plan = [
            ("get_session_info", client.a_get_session_info, {}),
            ("get_current_weather", client.a_get_current_weather, {}),
            ("get_weather_forecast", client.a_get_weather_forecast, {}),
            ("get_total_laps", client.a_get_total_laps, {}),
            ("get_current_track", client.a_get_current_track, {}),
            ("get_safety_car_status", client.a_get_safety_car_status, {}),
            ("get_pitstop_window_recommendation", client.a_get_pitstop_window_recommendation, {}),
            ("get_pitstop_rejoin_position", client.a_get_pitstop_rejoin_position, {}),
            ("get_race_standings", client.a_get_race_standings, {"limit": 5}),
            ("get_player_telemetry", client.a_get_player_telemetry, {}),
            ("get_recent_events", client.a_get_recent_events, {"limit": 3}),
            ("get_current_lap", client.a_get_current_lap, {}),
            ("get_num_remaining_laps", client.a_get_num_remaining_laps, {}),
            ("get_penalties", client.a_get_penalties, {}),
            ("get_penalties_by_player", client.a_get_penalties_by_player, {"name": "Ver"}),
            ("get_teammate_position", client.a_get_teammate_position, {}),
            ("get_player_position_by_name", client.a_get_player_position_by_name, {"name": "Ver"}),
            ("get_all_grid_positions", client.a_get_all_grid_positions, {}),
            ("get_safety_car_delta", client.a_get_safety_car_delta, {}),
            ("get_player_name_by_position", client.a_get_player_name_by_position, {"position": 1}),
            ("get_fastest_lap_data", client.a_get_fastest_lap_data, {}),
            ("get_penalities", client.a_get_penalities, {}),
            ("get_penalities_by_driver_name", client.a_get_penalities_by_driver_name, {"name": "Ver"}),
            ("get_drs_status", client.a_get_drs_status, {}),
            ("get_driver_by_position", client.a_get_driver_by_position, {"position": 1}),
            ("get_driver_by_name", client.a_get_driver_by_name, {"name": "Ver"}),
            ("get_top_drivers", client.a_get_top_drivers, {"count": 3}),
            ("get_race_summary", client.a_get_race_summary, {}),
            ("get_capture_stats", client.a_get_capture_stats, {}),
            ("get_current_position", client.a_get_current_position, {}),
            ("get_gap_to_driver_by_name", client.a_get_gap_to_driver_by_name, {"name": "Ver"}),
            ("get_gap_to_driver_by_position", client.a_get_gap_to_driver_by_position, {"position": 2}),
            ("get_gap_to_driver_in_front", client.a_get_gap_to_driver_in_front, {}),
            ("get_gap_to_driver_in_back", client.a_get_gap_to_driver_in_back, {}),
            ("get_fuel_status", client.a_get_fuel_status, {}),
            ("get_ers_status", client.a_get_ers_status, {}),
            ("get_tyres_status", client.a_get_tyres_status, {}),
            ("get_damage_status", client.a_get_damage_status, {}),
            ("get_car_telemetry_history", client.a_get_car_telemetry_history, {"car_index": 0, "limit": 3}),
            ("get_car_status_changes", client.a_get_car_status_changes, {"car_index": 0, "limit": 3}),
            ("get_car_damage_events", client.a_get_car_damage_events, {"car_index": 0, "limit": 3}),
            ("get_car_lap_history", client.a_get_car_lap_history, {"car_index": 0, "limit": 3}),
            ("get_session_changes", client.a_get_session_changes, {"limit": 3}),
            ("get_session_forecast", client.a_get_session_forecast, {"limit": 3}),
            ("get_safety_periods", client.a_get_safety_periods, {}),
        ]
        for tool, method, params in call_plan:
            _print(tool, await method(**params))

if __name__ == "__main__":
    asyncio.run(main())
