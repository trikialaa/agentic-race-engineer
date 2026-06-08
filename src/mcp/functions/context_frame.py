from __future__ import annotations

from typing import Any

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.functions._shared import (
    _abs_round,
    _clock_now,
    _normalize_flag,
    _normalize_safety_car,
    _normalize_tyre_compound,
    _parse_lap_time_seconds,
    _pit_status_value,
    _round,
    _strip_nulls,
)


def _level_low_medium_high(value: float | None) -> str:
    if value is None:
        return "low"
    if value >= 50:
        return "high"
    if value >= 20:
        return "medium"
    return "low"


def _damage_level(value: float | None) -> str:
    if value is None:
        return "undamaged"
    if value <= 10:
        return "undamaged"
    if value >= 50:
        return "high"
    if value >= 20:
        return "medium"
    return "low"


def _damage_by_part_levels(damage: dict[str, Any]) -> dict[str, str]:
    front_wing = damage.get("frontWingDamage")
    front_left = None
    front_right = None
    if isinstance(front_wing, (list, tuple)):
        front_left = _round(front_wing[0], 1) if len(front_wing) > 0 else None
        front_right = _round(front_wing[1], 1) if len(front_wing) > 1 else None
    front_wing_max = None
    wing_vals = [v for v in (front_left, front_right) if isinstance(v, (int, float))]
    if wing_vals:
        front_wing_max = max(float(v) for v in wing_vals)
    rear_wing = _round(damage.get("rearWingDamage"), 1)
    floor = _round(damage.get("floorDamage"), 1)
    diffuser = _round(damage.get("diffuserDamage"), 1)
    return {
        "frontWing": _damage_level(front_wing_max),
        "rearWing": _damage_level(rear_wing),
        "floor": _damage_level(floor),
        "diffuser": _damage_level(diffuser),
    }


def _session_phase(mode: str, safety_car: str, lap: int | None, laps_remaining: int | None) -> str:
    if mode != "in_game":
        return "not_racing"
    if safety_car in ("sc", "vsc"):
        return "sc_vsc"
    if isinstance(laps_remaining, int) and laps_remaining < 0:
        return "finishing"
    if lap == 1:
        return "opening_lap"
    return "racing"


def _pace_deltas(
    standings: list[dict[str, Any]], player_position: int | None, player_last_lap: Any
) -> tuple[float | None, float | None]:
    player_lap_s = _parse_lap_time_seconds(player_last_lap)
    if player_lap_s is None or not isinstance(player_position, int):
        return None, None
    front = next((row for row in standings if row.get("position") == player_position - 1), None)
    back = next((row for row in standings if row.get("position") == player_position + 1), None)
    front_s = _parse_lap_time_seconds((front or {}).get("lastLapTime"))
    back_s = _parse_lap_time_seconds((back or {}).get("lastLapTime"))
    delta_front = _round(front_s - player_lap_s, 3) if front_s is not None else None
    delta_back = _round(back_s - player_lap_s, 3) if back_s is not None else None
    return delta_front, delta_back


def _presence_mode(capture: F1TelemetryCapture) -> dict[str, Any]:
    presence = capture.query.get_player_presence_state()
    return {
        "mode": presence.get("state", "neither"),
        "sessionType": presence.get("sessionTypeName"),
        "gameMode": presence.get("gameModeName"),
        "track": presence.get("trackName"),
        "freshnessMs": int((presence.get("secondsSinceUpdate") or 0.0) * 1000),
        "lastUpdate": presence.get("lastUpdate"),
    }


def _player_visual_compound(capture: F1TelemetryCapture, player_idx: int | None) -> str | None:
    if not isinstance(player_idx, int) or player_idx < 0:
        return None
    try:
        _, arrays = capture.query._car_arrays(("car_status", "carStatus"))
        status_data = arrays[0] if arrays else []
        if player_idx < len(status_data):
            status = status_data[player_idx] if isinstance(status_data[player_idx], dict) else {}
            visual = status.get("visualTyreCompoundName")
            return _normalize_tyre_compound(visual)
    except Exception:
        return None
    return None


def _player_tyre_wear(capture: F1TelemetryCapture, player_idx: int | None) -> list[float] | None:
    if not isinstance(player_idx, int) or player_idx < 0:
        return None
    try:
        _, arrays = capture.query._car_arrays(("car_damage", "carDamage"))
        damage_data = arrays[0] if arrays else []
        if player_idx >= len(damage_data):
            return None
        damage = damage_data[player_idx] if isinstance(damage_data[player_idx], dict) else {}
        wear = damage.get("tyresWear")
        if wear is None:
            wear = damage.get("m_tyresWear")
        if isinstance(wear, (list, tuple)):
            values = [float(v) for v in wear if isinstance(v, (int, float))]
            return values if values else None
    except Exception:
        return None
    return None


def get_context_frame(capture: F1TelemetryCapture) -> dict[str, Any]:
    mode_data = _presence_mode(capture)
    session = capture.query.get_session_info()
    player = capture.query.get_current_position() or {}
    telemetry = capture.query.get_player_telemetry()
    fuel = capture.query.get_fuel_status()
    ers = capture.query.get_ers_status()
    tyres = capture.query.get_tyres_status()
    damage = capture.query.get_damage_status()
    weather = capture.query.get_current_weather()
    forecast = capture.query.get_weather_forecast()
    gap_front = capture.query.get_gap_to_driver_in_front()
    gap_back = capture.query.get_gap_to_driver_in_back()
    latest_forecast = forecast.get("latestForecast") if isinstance(forecast, dict) else {}
    telemetry_status = telemetry.get("status") or {}
    safety_car = _normalize_safety_car(capture.query.get_safety_car_status())
    flag = _normalize_flag(telemetry_status.get("flagColor"))
    lap = capture.query.get_current_lap()
    laps_total = session.get("totalLaps")
    laps_remaining = capture.query.get_num_remaining_laps()
    session_snapshot = capture.query._session_snapshot()
    low_fuel_mode = (
        session_snapshot.get("lowFuelMode") if isinstance(session_snapshot, dict) else None
    )
    low_fuel_mode_hard = low_fuel_mode == 1
    standings = capture.query.get_race_standings(limit=22)
    player_idx = capture.player_car_index
    # Grid (starting) position from lap data for the player's car
    try:
        _, _laps, _ = capture.query._lap_participant_snapshot()
        _player_lap = _laps[player_idx] if 0 <= player_idx < len(_laps) else {}
        start_position: int | None = _player_lap.get("gridPosition") or None
        if isinstance(start_position, int) and start_position <= 0:
            start_position = None
    except Exception:
        start_position = None
    fuel_laps_raw = _round(fuel.get("fuelRemainingLaps"), 2)
    fuel_laps_out = fuel_laps_raw
    fuel_delta_laps = (
        _round((fuel_laps_raw - laps_remaining), 2)
        if fuel_laps_raw is not None and laps_remaining is not None
        else None
    )
    player_position = player.get("position")
    front_driver = (
        capture.query.get_driver_by_position(player_position - 1)
        if isinstance(player_position, int) and player_position > 1
        else None
    )
    back_driver = (
        capture.query.get_driver_by_position(player_position + 1)
        if isinstance(player_position, int)
        else None
    )
    pace_delta_front_s, pace_delta_back_s = _pace_deltas(
        standings, player_position, player.get("lastLapTime")
    )
    gap_front_s = _abs_round((gap_front or {}).get("gapSecondsApprox"), 2)
    gap_back_s = _abs_round((gap_back or {}).get("gapSecondsApprox"), 2)
    visual_compound = _player_visual_compound(capture, player_idx) or _normalize_tyre_compound(
        telemetry_status.get("tyreCompound")
    )
    tyre_wear = _player_tyre_wear(capture, player_idx)
    active_positions = [
        pos for row in standings if isinstance(pos := row.get("position"), int) and pos > 0
    ]
    total_positions = max(active_positions) if active_positions else len(standings)
    if not total_positions:
        total_positions = 20
    result = {
        "time": _clock_now(),
        "context": {
            "session": {
                "type": session.get("sessionTypeName"),
                "track": session.get("trackName"),
                "lap": {
                    "current": lap,
                    "total": laps_total,
                },
                "lapsRemaining": laps_remaining,
                "phase": _session_phase(
                    mode_data.get("mode") or "neither", safety_car, lap, laps_remaining
                ),
            },
            "player": {
                "id": player_idx,
                "name": player.get("driverName"),
                "team": next(
                    (r.get("teamName") for r in standings if r.get("carIndex") == player_idx), None
                ),
                "position": {
                    "current": player_position,
                    "start": start_position,
                    "total": total_positions,
                },
                "gap": {
                    "frontS": gap_front_s,
                    "backS": gap_back_s,
                    "frontDriver": {
                        "name": (front_driver or {}).get("driverName"),
                        "position": (front_driver or {}).get("position"),
                    }
                    if front_driver
                    else None,
                    "backDriver": {
                        "name": (back_driver or {}).get("driverName"),
                        "position": (back_driver or {}).get("position"),
                    }
                    if back_driver
                    else None,
                },
                "pace": {
                    "lastLapS": _parse_lap_time_seconds(player.get("lastLapTime")),
                    "deltaFrontS": pace_delta_front_s,
                    "deltaBackS": pace_delta_back_s,
                },
                "car": {
                    "tyre": {
                        "compound": visual_compound,
                        "ageLaps": tyres.get("ageLaps"),
                        "wearLevel": _level_low_medium_high(
                            _round(sum(tyre_wear) / len(tyre_wear), 1) if tyre_wear else None
                        ),
                    },
                    "fuel": {
                        "status": "critical" if low_fuel_mode_hard else "nominal",
                        "lapsRemaining": fuel_laps_out,
                        "deltaLaps": fuel_delta_laps,
                    },
                    "ersPct": _round(ers.get("ersPercentage"), 1),
                    "damageByPart": _damage_by_part_levels(damage),
                    "pitStatus": _pit_status_value(player.get("pitStatus")),
                },
            },
            "raceControl": {
                "safetyCar": safety_car,
                "flag": flag,
            },
            "weather": {
                "type": weather.get("weatherName"),
                "trackTempC": weather.get("trackTemperature"),
                "airTempC": weather.get("airTemperature"),
                "rainRiskNext10mPct": (latest_forecast or {}).get("rainPercentage"),
            },
        },
    }
    return _strip_nulls(result)
