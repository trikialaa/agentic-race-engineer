from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from src.live_data_engine.capture import F1TelemetryCapture
_LAP_TIMES_STATE: Dict[int, Dict[str, Dict[str, Optional[str]]]] = {}


def _round(value: Any, digits: int = 1) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _clock_now() -> str:
    now = time.time()
    local = time.localtime(now)
    ms = int((now - int(now)) * 1000)
    return time.strftime("%H:%M:%S", local) + f".{ms:03d}"


def _parse_lap_time_seconds(value: Any) -> Optional[float]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text in ("00:00.000", "0:00.000"):
        return None
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    except Exception:
        return None


def _normalize_tyre_compound(compound: Any) -> Optional[str]:
    if not isinstance(compound, str) or not compound.strip():
        return None
    normalized = compound.strip().lower()
    mapping = {
        "soft": "soft",
        "medium": "medium",
        "hard": "hard",
        "inter": "inter",
        "wet": "wet",
    }
    if normalized in mapping:
        return mapping[normalized]
    if normalized.startswith("c"):
        return None
    if "inter" in normalized:
        return "inter"
    if "wet" in normalized:
        return "wet"
    return None


def _pit_status_value(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text == "none":
            return "none"
        return text
    return str(value)


def _abs_round(value: Any, digits: int = 2) -> Optional[float]:
    rounded = _round(value, digits)
    if rounded is None:
        return None
    return abs(rounded)


def _severity_from_damage(damage: Dict[str, Any]) -> str:
    points: List[float] = []
    tyre_wear = damage.get("tyreWear")
    if isinstance(tyre_wear, (list, tuple)):
        points.extend([float(v) for v in tyre_wear if isinstance(v, (int, float))])
    for key in ("rearWingDamage", "floorDamage", "diffuserDamage"):
        val = damage.get(key)
        if isinstance(val, (int, float)):
            points.append(float(val))
    fw = damage.get("frontWingDamage")
    if isinstance(fw, (list, tuple)):
        points.extend([float(v) for v in fw if isinstance(v, (int, float))])
    max_damage = max(points) if points else 0.0
    if max_damage >= 30:
        return "major"
    if max_damage >= 10:
        return "minor"
    return "none"


def _level_low_medium_high(value: Optional[float]) -> str:
    if value is None:
        return "low"
    if value >= 50:
        return "high"
    if value >= 20:
        return "medium"
    return "low"


def _damage_level(value: Optional[float]) -> str:
    if value is None:
        return "undamaged"
    if value <= 10:
        return "undamaged"
    if value >= 50:
        return "high"
    if value >= 20:
        return "medium"
    return "low"


def _damage_by_part_levels(damage: Dict[str, Any]) -> Dict[str, str]:
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


def _normalize_safety_car(value: Any) -> str:
    if not isinstance(value, str):
        return "none"
    text = value.strip().lower()
    if text in ("vsc", "virtual safety car"):
        return "vsc"
    if "safety car" in text and "no " not in text:
        return "sc"
    return "none"


def _normalize_flag(value: Any) -> str:
    if not isinstance(value, str):
        return "none"
    text = value.strip().lower()
    if not text or text == "none":
        return "none"
    if text == "invalid/unknown":
        return "none"
    return text


def _session_phase(mode: str, safety_car: str, lap: Optional[int], laps_remaining: Optional[int]) -> str:
    if mode != "in_game":
        return "not_racing"
    if safety_car in ("sc", "vsc"):
        return "sc_vsc"
    if laps_remaining == 0:
        return "finishing"
    if lap == 1:
        return "opening_lap"
    return "racing"


def _pace_deltas(standings: List[Dict[str, Any]], player_position: Optional[int], player_last_lap: Any) -> Tuple[Optional[float], Optional[float]]:
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


def _presence_mode(capture: F1TelemetryCapture) -> Dict[str, Any]:
    presence = capture.get_player_presence_state()
    return {
        "mode": presence.get("state", "neither"),
        "sessionType": presence.get("sessionTypeName"),
        "gameMode": presence.get("gameModeName"),
        "track": presence.get("trackName"),
        "freshnessMs": int((presence.get("secondsSinceUpdate") or 0.0) * 1000),
        "lastUpdate": presence.get("lastUpdate"),
    }


def _summary_line(
    mode: str,
    track: Optional[str],
    session_type: Optional[str],
    position: Optional[int],
    laps_remaining: Optional[int],
    sc_status: Optional[str],
) -> str:
    bits = [mode]
    if session_type:
        bits.append(session_type)
    if track:
        bits.append(track)
    if position:
        bits.append(f"P{position}")
    if laps_remaining is not None:
        bits.append(f"{laps_remaining} laps left")
    if sc_status:
        bits.append(sc_status)
    return " | ".join(bits)


def _envelope(capture: F1TelemetryCapture, summary: str, data: Dict[str, Any]) -> Dict[str, Any]:
    mode_data = _presence_mode(capture)
    return {
        "ok": True,
        "timestamp": time.time(),
        "freshnessMs": mode_data.get("freshnessMs"),
        "state": mode_data.get("mode"),
        "summary": summary,
        "data": data,
    }


def _player_visual_compound(capture: F1TelemetryCapture, player_idx: Optional[int]) -> Optional[str]:
    if not isinstance(player_idx, int) or player_idx < 0:
        return None
    try:
        _, arrays = capture._car_arrays(("car_status", "carStatus"))
        status_data = arrays[0] if arrays else []
        if player_idx < len(status_data):
            status = status_data[player_idx] if isinstance(status_data[player_idx], dict) else {}
            visual = status.get("visualTyreCompoundName")
            return _normalize_tyre_compound(visual)
    except Exception:
        return None
    return None


def _player_tyre_wear(capture: F1TelemetryCapture, player_idx: Optional[int]) -> Optional[List[float]]:
    if not isinstance(player_idx, int) or player_idx < 0:
        return None
    try:
        _, arrays = capture._car_arrays(("car_damage", "carDamage"))
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


def get_context_frame(capture: F1TelemetryCapture) -> Dict[str, Any]:
    mode_data = _presence_mode(capture)
    session = capture.get_session_info()
    player = capture.get_current_position() or {}
    telemetry = capture.get_player_telemetry()
    fuel = capture.get_fuel_status()
    ers = capture.get_ers_status()
    tyres = capture.get_tyres_status()
    damage = capture.get_damage_status()
    drs = capture.get_drs_status()
    weather = capture.get_current_weather()
    forecast = capture.get_weather_forecast()
    gap_front = capture.get_gap_to_driver_in_front()
    gap_back = capture.get_gap_to_driver_in_back()
    latest_forecast = forecast.get("latestForecast") if isinstance(forecast, dict) else {}
    telemetry_status = telemetry.get("status") or {}
    safety_car = _normalize_safety_car(capture.get_safety_car_status())
    flag = _normalize_flag(telemetry_status.get("flagColor"))
    lap = capture.get_current_lap()
    laps_total = session.get("totalLaps")
    laps_remaining = capture.get_num_remaining_laps()
    session_snapshot = capture._session_snapshot()
    low_fuel_mode = session_snapshot.get("lowFuelMode") if isinstance(session_snapshot, dict) else None
    low_fuel_mode_hard = (low_fuel_mode == 1)
    standings = capture.get_race_standings(limit=22)
    player_idx = capture.player_car_index
    fuel_laps = _round(fuel.get("fuelRemainingLaps"), 2)
    if not low_fuel_mode_hard and isinstance(laps_remaining, int) and laps_remaining >= 0:
        fuel_laps = float(laps_remaining)
    fuel_delta_laps = (
        _round((fuel_laps - laps_remaining), 2)
        if fuel_laps is not None and laps_remaining is not None
        else None
    )
    if not low_fuel_mode_hard and fuel_delta_laps is not None and fuel_delta_laps < 0:
        fuel_delta_laps = 0.0
    player_position = player.get("position")
    front_driver = capture.get_driver_by_position(player_position - 1) if isinstance(player_position, int) and player_position > 1 else None
    back_driver = capture.get_driver_by_position(player_position + 1) if isinstance(player_position, int) else None
    pace_delta_front_s, pace_delta_back_s = _pace_deltas(standings, player_position, player.get("lastLapTime"))
    gap_front_s = _abs_round((gap_front or {}).get("gapSecondsApprox"), 2)
    gap_back_s = _abs_round((gap_back or {}).get("gapSecondsApprox"), 2)
    visual_compound = _player_visual_compound(capture, player_idx) or _normalize_tyre_compound(telemetry_status.get("tyreCompound"))
    tyre_wear = _player_tyre_wear(capture, player_idx)
    active_positions = [row.get("position") for row in standings if isinstance(row.get("position"), int) and row.get("position") > 0]
    total_positions = max(active_positions) if active_positions else len(standings)
    if not total_positions:
        total_positions = 20
    return {
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
                "phase": _session_phase(mode_data.get("mode") or "neither", safety_car, lap, laps_remaining),
            },
            "player": {
                "id": player_idx,
                "name": player.get("driverName"),
                "position": {
                    "current": player_position,
                    "total": total_positions,
                },
                "gap": {
                    "frontS": gap_front_s,
                    "backS": gap_back_s,
                    "frontDriver": {
                        "name": (front_driver or {}).get("driverName"),
                        "position": (front_driver or {}).get("position"),
                    } if front_driver else None,
                    "backDriver": {
                        "name": (back_driver or {}).get("driverName"),
                        "position": (back_driver or {}).get("position"),
                    } if back_driver else None,
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
                        "wearLevel": _level_low_medium_high(_round(sum(tyre_wear) / len(tyre_wear), 1) if tyre_wear else None),
                    },
                    "fuelLaps": fuel_laps,
                    "fuelDeltaLaps": fuel_delta_laps,
                    "ersPct": _round(ers.get("ersPercentage"), 1),
                    "drs": {
                        "status": drs.get("drsStatus"),
                        "available": drs.get("drsAvailable"),
                        "fault": drs.get("drsFault") if drs.get("drsFault") is not None else "none",
                    },
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


def get_session_state(capture: F1TelemetryCapture) -> Dict[str, Any]:
    mode_data = _presence_mode(capture)
    session = capture.get_session_info()
    data = {
        "mode": mode_data.get("mode"),
        "sessionType": session.get("sessionTypeName"),
        "gameMode": mode_data.get("gameMode"),
        "track": session.get("trackName"),
        "lap": capture.get_current_lap(),
        "lapsTotal": session.get("totalLaps"),
        "lapsRemaining": capture.get_num_remaining_laps(),
        "safetyCar": capture.get_safety_car_status(),
        "freshnessMs": mode_data.get("freshnessMs"),
    }
    return _envelope(
        capture,
        summary=_summary_line(
            mode=data.get("mode") or "neither",
            track=data.get("track"),
            session_type=data.get("sessionType"),
            position=None,
            laps_remaining=data.get("lapsRemaining"),
            sc_status=data.get("safetyCar"),
        ),
        data=data,
    )


def get_weather_brief(capture: F1TelemetryCapture, points: int = 3) -> Dict[str, Any]:
    weather = capture.get_current_weather()
    forecast = capture.get_weather_forecast()
    samples = forecast.get("forecastSamples") if isinstance(forecast, dict) else []
    if not isinstance(samples, list):
        samples = []
    concise_samples = []
    for sample in samples[: max(0, points)]:
        if not isinstance(sample, dict):
            continue
        concise_samples.append(
            {
                "offsetMin": sample.get("timeOffset"),
                "weather": sample.get("weatherName"),
                "rainPct": sample.get("rainPercentage"),
                "trackTempC": sample.get("trackTemp"),
                "airTempC": sample.get("airTemp"),
            }
        )
    data = {
        "now": {
            "weather": weather.get("weatherName"),
            "trackTempC": weather.get("trackTemperature"),
            "airTempC": weather.get("airTemperature"),
        },
        "forecast": concise_samples,
    }
    summary = f"{data['now']['weather']} now, next rain risk {concise_samples[0]['rainPct']}%" if concise_samples else f"{data['now']['weather']} now"
    return _envelope(capture, summary=summary, data=data)


def get_strategy_brief(capture: F1TelemetryCapture) -> Dict[str, Any]:
    fuel = capture.get_fuel_status()
    ers = capture.get_ers_status()
    tyres = capture.get_tyres_status()
    damage = capture.get_damage_status()
    penalties = capture.get_penalties()
    pit_window = capture.get_pitstop_window_recommendation()
    data = {
        "fuel": {
            "pct": _round(fuel.get("fuelPercentage"), 1),
            "laps": _round(fuel.get("fuelRemainingLaps"), 2),
            "mix": fuel.get("fuelMixName"),
            "critical": bool(fuel.get("fuelCritical")),
        },
        "ers": {
            "pct": _round(ers.get("ersPercentage"), 1),
            "mode": ers.get("ersDeployModeName"),
        },
        "tyres": {
            "compound": tyres.get("compound"),
            "ageLaps": tyres.get("ageLaps"),
            "old": tyres.get("tyresOld"),
        },
        "damageLevel": _severity_from_damage(damage),
        "penalties": penalties.get("penaltiesFormatted"),
        "pitWindow": pit_window,
        "pitRejoinPosition": capture.get_pitstop_rejoin_position(),
    }
    summary = f"Fuel {data['fuel']['laps']} laps, ERS {data['ers']['pct']}%, tyres {data['tyres']['compound']} age {data['tyres']['ageLaps']}"
    return _envelope(capture, summary=summary, data=data)


def get_player_brief(capture: F1TelemetryCapture) -> Dict[str, Any]:
    pos = capture.get_current_position() or {}
    telem = capture.get_player_telemetry()
    fuel = capture.get_fuel_status()
    ers = capture.get_ers_status()
    tyres = capture.get_tyres_status()
    damage = capture.get_damage_status()
    gap_front = capture.get_gap_to_driver_in_front()
    gap_back = capture.get_gap_to_driver_in_back()
    telemetry_data = telem.get("telemetry") or {}
    data = {
        "driver": pos.get("driverName"),
        "position": pos.get("position"),
        "currentLap": pos.get("currentLap"),
        "speedKph": telemetry_data.get("speedKph"),
        "lastLap": pos.get("lastLapTime"),
        "gapFrontS": _round((gap_front or {}).get("gapSecondsApprox"), 2),
        "gapBackS": _round((gap_back or {}).get("gapSecondsApprox"), 2),
        "fuelLaps": _round(fuel.get("fuelRemainingLaps"), 2),
        "fuelCritical": bool(fuel.get("fuelCritical")),
        "ersPct": _round(ers.get("ersPercentage"), 1),
        "tyreCompound": tyres.get("compound"),
        "tyreAgeLaps": tyres.get("ageLaps"),
        "damageLevel": _severity_from_damage(damage),
        "warnings": telemetry_data.get("warnings"),
    }
    summary = (
        f"P{data.get('position')} {data.get('driver')}, "
        f"front gap {data.get('gapFrontS')}s, fuel {data.get('fuelLaps')} laps, ERS {data.get('ersPct')}%"
    )
    return _envelope(capture, summary=summary, data=data)


def get_race_brief(capture: F1TelemetryCapture) -> Dict[str, Any]:
    state = get_session_state(capture)["data"]
    player = get_player_brief(capture)["data"]
    weather = get_weather_brief(capture, points=1)["data"]
    data = {
        "state": state,
        "player": player,
        "weatherNow": weather.get("now"),
    }
    summary = _summary_line(
        mode=state.get("mode") or "neither",
        track=state.get("track"),
        session_type=state.get("sessionType"),
        position=player.get("position"),
        laps_remaining=state.get("lapsRemaining"),
        sc_status=state.get("safetyCar"),
    )
    return _envelope(capture, summary=summary, data=data)


def _format_gap_value(lap_diff: Optional[int], delta_ms: Any) -> Optional[str]:
    if isinstance(lap_diff, int) and lap_diff >= 1:
        return f"+{lap_diff} Lap" if lap_diff == 1 else f"+{lap_diff} Laps"
    if isinstance(delta_ms, (int, float)):
        return f"+{max(float(delta_ms), 0.0) / 1000.0:.3f}s"
    return None


def _position_change_since_start(current_position: Any, grid_position: Any) -> Optional[str]:
    if not isinstance(current_position, int) or current_position <= 0:
        return None
    if not isinstance(grid_position, int) or grid_position <= 0:
        return None
    delta = grid_position - current_position
    if delta >= 0:
        return f"{delta} gained"
    return f"{abs(delta)} lost"


def _is_retired_status(result_status: Any, driver_status: Any) -> bool:
    text = " ".join(
        part.strip().lower()
        for part in (str(result_status or ""), str(driver_status or ""))
        if isinstance(part, str)
    )
    keywords = (
        "retired",
        "disqualified",
        "did not finish",
        "did not start",
        "dnf",
        "dns",
        "dq",
        "excluded",
    )
    return any(token in text for token in keywords)


def _unserved_penalties_from_lap(lap: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seconds = lap.get("penalties")
    if isinstance(seconds, (int, float)) and seconds > 0:
        out.append(f"{int(seconds)}s penalty")
    stop_go = lap.get("numUnservedStopGoPens")
    if isinstance(stop_go, int) and stop_go > 0:
        out.append("Stop and go penalty" if stop_go == 1 else f"{stop_go}x stop and go penalties")
    drive_through = lap.get("numUnservedDriveThroughPens")
    if isinstance(drive_through, int) and drive_through > 0:
        out.append("Drive through penalty" if drive_through == 1 else f"{drive_through}x drive through penalties")
    formatted = lap.get("penaltiesFormatted")
    if isinstance(formatted, str):
        text = formatted.strip()
        if text and text.lower() != "none" and "warning" not in text.lower():
            if "grid" in text.lower() and text not in out:
                out.append(text)
    return out


def _parse_time_to_ms(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return int(round((minutes * 60 + seconds) * 1000))
        except Exception:
            return None
    try:
        return int(round(float(text) * 1000))
    except Exception:
        return None


def _format_ms_as_lap(ms: Optional[int]) -> Optional[str]:
    if not isinstance(ms, int) or ms <= 0:
        return None
    minutes = ms // 60000
    seconds = (ms % 60000) / 1000.0
    return f"{minutes:02d}:{seconds:06.3f}"


def _format_ms_as_sector(ms: Optional[int]) -> Optional[str]:
    if not isinstance(ms, int) or ms <= 0:
        return None
    seconds = ms / 1000.0
    return f"{seconds:.3f}"


def _pick_time_text(*values: Any) -> Optional[str]:
    zero_tokens = {"00:00.000", "0:00.000", "00.000", "0.000", "0"}
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text and text not in zero_tokens:
                return text
    return None


def _derive_sector3_ms(last_lap_ms: Optional[int], s1_ms: Optional[int], s2_ms: Optional[int]) -> Optional[int]:
    if not isinstance(last_lap_ms, int) or not isinstance(s1_ms, int) or not isinstance(s2_ms, int):
        return None
    if last_lap_ms <= 0 or s1_ms <= 0 or s2_ms <= 0:
        return None
    s3 = last_lap_ms - s1_ms - s2_ms
    if s3 <= 0:
        return None
    return s3


def _is_better_time(new_value: Optional[str], current_best: Optional[str]) -> bool:
    if not isinstance(new_value, str) or not new_value.strip():
        return False
    new_ms = _parse_time_to_ms(new_value)
    if new_ms is None or new_ms <= 0:
        return False
    if not isinstance(current_best, str) or not current_best.strip():
        return True
    best_ms = _parse_time_to_ms(current_best)
    if best_ms is None or best_ms <= 0:
        return True
    return new_ms < best_ms


def _derive_sector3_text(lap_text: Optional[str], s1_text: Optional[str], s2_text: Optional[str]) -> Optional[str]:
    lap_ms = _parse_time_to_ms(lap_text)
    s1_ms = _parse_time_to_ms(s1_text)
    s2_ms = _parse_time_to_ms(s2_text)
    s3_ms = _derive_sector3_ms(lap_ms, s1_ms, s2_ms)
    return _format_ms_as_sector(s3_ms) if isinstance(s3_ms, int) and s3_ms > 0 else None


def get_leaderboard(capture: F1TelemetryCapture) -> Dict[str, Any]:
    standings = capture.get_race_standings(limit=22)
    _, lap_data, _ = capture._lap_participant_snapshot()
    laps_by_car = {idx: lap for idx, lap in enumerate(lap_data) if isinstance(lap, dict)}
    _, arrays = capture._car_arrays(("car_status", "carStatus"))
    status_data = arrays[0] if arrays else []

    leaderboard = []
    for row in standings:
        position = row.get("position")
        if not isinstance(position, int) or position <= 0:
            continue
        car_id = row.get("carIndex")
        lap = laps_by_car.get(car_id, {}) if isinstance(car_id, int) else {}
        leader_lap_diff = lap.get("deltaToRaceLeaderInMS")
        ahead_lap_diff = lap.get("deltaToCarInFrontInMS")
        current_lap = lap.get("currentLapNum")
        leader_current_lap = None
        ahead_current_lap = None
        if standings:
            leader = standings[0]
            leader_lap = laps_by_car.get(leader.get("carIndex"), {}) if isinstance(leader.get("carIndex"), int) else {}
            leader_current_lap = leader_lap.get("currentLapNum")
        if isinstance(position, int) and position > 1:
            ahead_driver = next((d for d in standings if d.get("position") == position - 1), None)
            if ahead_driver and isinstance(ahead_driver.get("carIndex"), int):
                ahead_lap = laps_by_car.get(ahead_driver.get("carIndex"), {}) or {}
                ahead_current_lap = ahead_lap.get("currentLapNum")

        laps_to_leader = (leader_current_lap - current_lap) if isinstance(leader_current_lap, int) and isinstance(current_lap, int) else None
        laps_to_ahead = (ahead_current_lap - current_lap) if isinstance(ahead_current_lap, int) and isinstance(current_lap, int) else None

        visible_compound = None
        tyre_age_laps = None
        if isinstance(car_id, int) and 0 <= car_id < len(status_data):
            car_status = status_data[car_id] if isinstance(status_data[car_id], dict) else {}
            visible_compound = car_status.get("visualTyreCompoundName") or car_status.get("actualTyreCompoundName")
            tyre_age_laps = car_status.get("tyresAgeLaps")

        pit_status_name = lap.get("pitStatusName")
        is_in_pit = isinstance(pit_status_name, str) and "pit" in pit_status_name.strip().lower()
        result_status_name = lap.get("resultStatusName") or row.get("resultStatus")
        driver_status_name = lap.get("driverStatusName") or row.get("driverStatus")

        leaderboard.append(
            {
                "position": position,
                "carId": car_id,
                "driver": row.get("driverName"),
                "team": row.get("teamName"),
                "gapToLeader": "LEADER" if position == 1 else _format_gap_value(laps_to_leader, leader_lap_diff),
                "gapToAhead": "LEADER" if position == 1 else _format_gap_value(laps_to_ahead, ahead_lap_diff),
                "visibleTyreCompound": visible_compound,
                "tyreAgeLaps": tyre_age_laps,
                "positionChangeSinceStart": _position_change_since_start(position, lap.get("gridPosition")),
                "numberPitStops": lap.get("numPitStops"),
                "unservedPenalties": _unserved_penalties_from_lap(lap),
                "isInPit": bool(is_in_pit),
                "isRetired": _is_retired_status(result_status_name, driver_status_name),
                "isPlayer": bool(row.get("isPlayer")),
            }
        )

    return {
        "time": _clock_now(),
        "leaderboard": leaderboard,
    }


def get_lap_times(capture: F1TelemetryCapture) -> Dict[str, Any]:
    with capture.lock:
        session_history_by_car = list(getattr(capture, "session_history_by_car", []))
    standings = capture.get_race_standings(limit=22)
    _, lap_data, _ = capture._lap_participant_snapshot()
    lap_history = (capture.data.get("lap_data", {}) or {}).get("history", [])

    rows = []
    for row in standings:
        position = row.get("position")
        car_id = row.get("carIndex")
        if not isinstance(position, int) or position <= 0 or not isinstance(car_id, int):
            continue

        lap = lap_data[car_id] if 0 <= car_id < len(lap_data) and isinstance(lap_data[car_id], dict) else {}
        history_entries = lap_history[car_id] if 0 <= car_id < len(lap_history) and isinstance(lap_history[car_id], list) else []
        latest_history = history_entries[0] if history_entries else {}
        recent_lap_text = _pick_time_text((latest_history or {}).get("lapTimeFormatted"), lap.get("lastLapTimeFormatted"))
        recent_s1_text = _pick_time_text((latest_history or {}).get("sector1"), lap.get("sector1TimeFormatted"))
        recent_s2_text = _pick_time_text((latest_history or {}).get("sector2"), lap.get("sector2TimeFormatted"))
        recent_s3_text = _pick_time_text((latest_history or {}).get("sector3"))
        recent_lap_ms = _parse_time_to_ms(latest_history.get("lapTimeFormatted")) if isinstance(latest_history, dict) else None
        recent_s1_ms = _parse_time_to_ms(latest_history.get("sector1")) if isinstance(latest_history, dict) else None
        recent_s2_ms = _parse_time_to_ms(latest_history.get("sector2")) if isinstance(latest_history, dict) else None
        recent_s3_ms = _parse_time_to_ms(latest_history.get("sector3")) if isinstance(latest_history, dict) else None
        if recent_s3_ms is None:
            recent_s3_ms = _derive_sector3_ms(recent_lap_ms, recent_s1_ms, recent_s2_ms)

        # Fallback to live lap snapshot if history is not populated yet.
        if recent_lap_ms is None:
            recent_lap_ms = _parse_time_to_ms(lap.get("lastLapTimeFormatted"))
        if recent_s1_ms is None:
            recent_s1_ms = _parse_time_to_ms(lap.get("sector1TimeFormatted"))
            if not isinstance(recent_s1_ms, int) or recent_s1_ms <= 0:
                raw_s1 = lap.get("sector1TimeInMS")
                recent_s1_ms = int(raw_s1) if isinstance(raw_s1, (int, float)) and raw_s1 > 0 else None
        if recent_s2_ms is None:
            recent_s2_ms = _parse_time_to_ms(lap.get("sector2TimeFormatted"))
            if not isinstance(recent_s2_ms, int) or recent_s2_ms <= 0:
                raw_s2 = lap.get("sector2TimeInMS")
                recent_s2_ms = int(raw_s2) if isinstance(raw_s2, (int, float)) and raw_s2 > 0 else None
        if recent_s3_ms is None:
            recent_s3_ms = _derive_sector3_ms(recent_lap_ms, recent_s1_ms, recent_s2_ms)

        # Prefer per-car session history (completed laps, stable at line crossing).
        session_hist = session_history_by_car[car_id] if 0 <= car_id < len(session_history_by_car) else None
        if isinstance(session_hist, dict):
            sh_laps = session_hist.get("lapHistory")
            num_laps = session_hist.get("numLaps")
            if isinstance(sh_laps, list) and isinstance(num_laps, int) and num_laps > 0:
                max_idx = min(len(sh_laps), num_laps) - 1
                recent_complete = None
                for idx in range(max_idx, -1, -1):
                    lap_entry = sh_laps[idx]
                    if not isinstance(lap_entry, dict):
                        continue
                    flags = lap_entry.get("validFlags")
                    lap_ms = lap_entry.get("lapTimeInMS")
                    s1_ms = lap_entry.get("s1InMS")
                    s2_ms = lap_entry.get("s2InMS")
                    s3_ms = lap_entry.get("s3InMS")
                    all_valid = isinstance(flags, int) and (flags & 0x0F) == 0x0F
                    all_nonzero = all(
                        isinstance(v, int) and v > 0 for v in (lap_ms, s1_ms, s2_ms, s3_ms)
                    )
                    if all_valid and all_nonzero:
                        recent_complete = lap_entry
                        break

                if isinstance(recent_complete, dict):
                    recent_lap_ms = int(recent_complete.get("lapTimeInMS"))
                    recent_s1_ms = int(recent_complete.get("s1InMS"))
                    recent_s2_ms = int(recent_complete.get("s2InMS"))
                    recent_s3_ms = int(recent_complete.get("s3InMS"))
                    recent_lap_text = _pick_time_text(recent_complete.get("lapTimeFormatted"), recent_lap_text)
                    recent_s1_text = _pick_time_text(recent_complete.get("s1"), recent_s1_text)
                    recent_s2_text = _pick_time_text(recent_complete.get("s2"), recent_s2_text)
                    recent_s3_text = _pick_time_text(recent_complete.get("s3"), recent_s3_text)

        # Seed best values with current-most-recent valid timings so "best" is never
        # behind when history buffers lag by one update.
        best_lap_ms: Optional[int] = recent_lap_ms if isinstance(recent_lap_ms, int) and recent_lap_ms > 0 else None
        best_s1_ms: Optional[int] = recent_s1_ms if isinstance(recent_s1_ms, int) and recent_s1_ms > 0 else None
        best_s2_ms: Optional[int] = recent_s2_ms if isinstance(recent_s2_ms, int) and recent_s2_ms > 0 else None
        best_s3_ms: Optional[int] = recent_s3_ms if isinstance(recent_s3_ms, int) and recent_s3_ms > 0 else None
        best_lap_text = recent_lap_text
        best_s1_text = recent_s1_text
        best_s2_text = recent_s2_text
        best_s3_text = recent_s3_text
        for entry in history_entries:
            if not isinstance(entry, dict):
                continue
            e_lap_ms = _parse_time_to_ms(entry.get("lapTimeFormatted"))
            e_s1_ms = _parse_time_to_ms(entry.get("sector1"))
            e_s2_ms = _parse_time_to_ms(entry.get("sector2"))
            e_s3_ms = _parse_time_to_ms(entry.get("sector3"))
            e_lap_text = _pick_time_text(entry.get("lapTimeFormatted"))
            e_s1_text = _pick_time_text(entry.get("sector1"))
            e_s2_text = _pick_time_text(entry.get("sector2"))
            e_s3_text = _pick_time_text(entry.get("sector3"))
            if e_s3_ms is None:
                e_s3_ms = _derive_sector3_ms(e_lap_ms, e_s1_ms, e_s2_ms)
            if e_s3_text is None and isinstance(e_s3_ms, int) and e_s3_ms > 0:
                e_s3_text = _format_ms_as_sector(e_s3_ms)

            if isinstance(e_lap_ms, int) and (best_lap_ms is None or e_lap_ms < best_lap_ms):
                best_lap_ms = e_lap_ms
                best_lap_text = e_lap_text or best_lap_text
            if isinstance(e_s1_ms, int) and (best_s1_ms is None or e_s1_ms < best_s1_ms):
                best_s1_ms = e_s1_ms
                best_s1_text = e_s1_text or best_s1_text
            if isinstance(e_s2_ms, int) and (best_s2_ms is None or e_s2_ms < best_s2_ms):
                best_s2_ms = e_s2_ms
                best_s2_text = e_s2_text or best_s2_text
            if isinstance(e_s3_ms, int) and (best_s3_ms is None or e_s3_ms < best_s3_ms):
                best_s3_ms = e_s3_ms
                best_s3_text = e_s3_text or best_s3_text

        if isinstance(session_hist, dict):
            sh_laps = session_hist.get("lapHistory")
            if isinstance(sh_laps, list):
                for lap_entry in sh_laps:
                    if not isinstance(lap_entry, dict):
                        continue
                    flags = lap_entry.get("validFlags")
                    if not isinstance(flags, int):
                        continue

                    lap_v = lap_entry.get("lapTimeInMS")
                    if (flags & 0x01) and isinstance(lap_v, int) and lap_v > 0 and (best_lap_ms is None or lap_v < best_lap_ms):
                        best_lap_ms = lap_v
                        best_lap_text = _pick_time_text(lap_entry.get("lapTimeFormatted"), best_lap_text)

                    s1_v = lap_entry.get("s1InMS")
                    if (flags & 0x02) and isinstance(s1_v, int) and s1_v > 0 and (best_s1_ms is None or s1_v < best_s1_ms):
                        best_s1_ms = s1_v
                        best_s1_text = _pick_time_text(lap_entry.get("s1"), best_s1_text)

                    s2_v = lap_entry.get("s2InMS")
                    if (flags & 0x04) and isinstance(s2_v, int) and s2_v > 0 and (best_s2_ms is None or s2_v < best_s2_ms):
                        best_s2_ms = s2_v
                        best_s2_text = _pick_time_text(lap_entry.get("s2"), best_s2_text)

                    s3_v = lap_entry.get("s3InMS")
                    if (flags & 0x08) and isinstance(s3_v, int) and s3_v > 0 and (best_s3_ms is None or s3_v < best_s3_ms):
                        best_s3_ms = s3_v
                        best_s3_text = _pick_time_text(lap_entry.get("s3"), best_s3_text)

        rows.append(
            {}
        )

        most_recent_candidate = {
            "sector1": _format_ms_as_sector(recent_s1_ms) or recent_s1_text,
            "sector2": _format_ms_as_sector(recent_s2_ms) or recent_s2_text,
            "sector3": _format_ms_as_sector(recent_s3_ms) or recent_s3_text,
            "lap": _format_ms_as_lap(recent_lap_ms) or recent_lap_text,
        }
        best_candidate = {
            "sector1": _format_ms_as_sector(best_s1_ms) or best_s1_text,
            "sector2": _format_ms_as_sector(best_s2_ms) or best_s2_text,
            "sector3": _format_ms_as_sector(best_s3_ms) or best_s3_text,
            "lap": _format_ms_as_lap(best_lap_ms) or best_lap_text,
        }

        state = _LAP_TIMES_STATE.get(car_id)
        if not isinstance(state, dict):
            state = {
                "mostRecent": {"sector1": None, "sector2": None, "sector3": None, "lap": None},
                "best": {"sector1": None, "sector2": None, "sector3": None, "lap": None},
            }

        most_recent_out = dict(state.get("mostRecent", {}))
        best_out = dict(state.get("best", {}))
        for key in ("sector1", "sector2", "sector3", "lap"):
            candidate = most_recent_candidate.get(key)
            if candidate is not None:
                most_recent_out[key] = candidate
                if _is_better_time(candidate, best_out.get(key)):
                    best_out[key] = candidate
            best_candidate_value = best_candidate.get(key)
            if _is_better_time(best_candidate_value, best_out.get(key)):
                best_out[key] = best_candidate_value

        # Enforce non-null output where we have any known value.
        for key in ("sector1", "sector2", "sector3", "lap"):
            if most_recent_out.get(key) is None and best_out.get(key) is not None:
                most_recent_out[key] = best_out.get(key)
            if best_out.get(key) is None and most_recent_out.get(key) is not None:
                best_out[key] = most_recent_out.get(key)

        if most_recent_out.get("sector3") is None:
            derived = _derive_sector3_text(
                most_recent_out.get("lap"),
                most_recent_out.get("sector1"),
                most_recent_out.get("sector2"),
            )
            if derived is not None:
                most_recent_out["sector3"] = derived
                if _is_better_time(derived, best_out.get("sector3")):
                    best_out["sector3"] = derived

        if best_out.get("sector3") is None:
            derived_best = _derive_sector3_text(
                best_out.get("lap"),
                best_out.get("sector1"),
                best_out.get("sector2"),
            )
            if derived_best is not None:
                best_out["sector3"] = derived_best

        _LAP_TIMES_STATE[car_id] = {"mostRecent": most_recent_out, "best": best_out}

        rows[-1] = {
            "position": position,
            "carId": car_id,
            "driver": row.get("driverName"),
            "mostRecent": most_recent_out,
            "best": best_out,
        }

    return {
        "time": _clock_now(),
        "lapTimes": rows,
    }


def get_weather_forecast(capture: F1TelemetryCapture) -> Dict[str, Any]:
    weather_now = capture.get_current_weather()
    forecast = capture.get_weather_forecast()
    raw_samples = forecast.get("forecastSamples") if isinstance(forecast, dict) else []
    samples = raw_samples if isinstance(raw_samples, list) else []

    detailed_forecast = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        offset = sample.get("timeOffset")
        weather_name = sample.get("weatherName")
        rain_pct = sample.get("rainPercentage")
        track_temp = sample.get("trackTemp")
        air_temp = sample.get("airTemp")
        if offset is None and weather_name is None and rain_pct is None and track_temp is None and air_temp is None:
            continue
        detailed_forecast.append(
            {
                "offsetMin": offset,
                "weather": weather_name,
                "rainPct": rain_pct,
                "trackTempC": track_temp,
                "airTempC": air_temp,
            }
        )

    return {
        "time": _clock_now(),
        "current": {
            "weather": weather_now.get("weatherName"),
            "trackTempC": weather_now.get("trackTemperature"),
            "airTempC": weather_now.get("airTemperature"),
        },
        "forecast": detailed_forecast,
    }
