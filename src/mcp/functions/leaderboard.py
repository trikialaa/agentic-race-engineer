from __future__ import annotations

from typing import Any

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.functions._shared import _clock_now, _normalize_tyre_compound, _strip_nulls


def _format_gap_value(lap_diff: int | None, delta_ms: Any) -> str | None:
    if isinstance(lap_diff, int) and lap_diff >= 1:
        return f"+{lap_diff} Lap" if lap_diff == 1 else f"+{lap_diff} Laps"
    if isinstance(delta_ms, (int, float)):
        return f"+{max(float(delta_ms), 0.0) / 1000.0:.3f}s"
    return None


def _position_change_since_start(current_position: Any, grid_position: Any) -> str | None:
    if not isinstance(current_position, int) or current_position <= 0:
        return None
    if not isinstance(grid_position, int) or grid_position <= 0:
        return None
    delta = grid_position - current_position
    if delta == 0:
        return None
    if delta > 0:
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


def _unserved_penalties_from_lap(lap: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seconds = lap.get("penalties")
    if isinstance(seconds, (int, float)) and seconds > 0:
        out.append(f"{int(seconds)}s penalty")
    stop_go = lap.get("numUnservedStopGoPens")
    if isinstance(stop_go, int) and stop_go > 0:
        out.append("Stop and go penalty" if stop_go == 1 else f"{stop_go}x stop and go penalties")
    drive_through = lap.get("numUnservedDriveThroughPens")
    if isinstance(drive_through, int) and drive_through > 0:
        out.append(
            "Drive through penalty"
            if drive_through == 1
            else f"{drive_through}x drive through penalties"
        )
    formatted = lap.get("penaltiesFormatted")
    if isinstance(formatted, str):
        text = formatted.strip()
        if text and text.lower() != "none" and "warning" not in text.lower():
            if "grid" in text.lower() and text not in out:
                out.append(text)
    return out


def get_leaderboard(capture: F1TelemetryCapture) -> dict[str, Any]:
    standings = capture.query.get_race_standings(limit=22)
    _, lap_data, _ = capture.query._lap_participant_snapshot()
    laps_by_car = {idx: lap for idx, lap in enumerate(lap_data) if isinstance(lap, dict)}
    _, arrays = capture.query._car_arrays(("car_status", "carStatus"))
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
            leader_car_idx = leader.get("carIndex")
            leader_lap = (
                laps_by_car.get(leader_car_idx, {}) if isinstance(leader_car_idx, int) else {}
            )
            leader_current_lap = leader_lap.get("currentLapNum")
        if isinstance(position, int) and position > 1:
            ahead_driver = next((d for d in standings if d.get("position") == position - 1), None)
            if ahead_driver:
                ahead_car_idx = ahead_driver.get("carIndex")
                if isinstance(ahead_car_idx, int):
                    ahead_lap = laps_by_car.get(ahead_car_idx, {}) or {}
                    ahead_current_lap = ahead_lap.get("currentLapNum")

        raw_laps_to_leader = (
            (leader_current_lap - current_lap)
            if isinstance(leader_current_lap, int) and isinstance(current_lap, int)
            else None
        )
        raw_laps_to_ahead = (
            (ahead_current_lap - current_lap)
            if isinstance(ahead_current_lap, int) and isinstance(current_lap, int)
            else None
        )
        # Only trust lap-count diff when the time gap confirms the car is genuinely lapped.
        # At lap-crossing boundaries, currentLapNum briefly differs by 1 even for cars racing within seconds of each other.
        laps_to_leader = (
            raw_laps_to_leader
            if (
                isinstance(raw_laps_to_leader, int)
                and raw_laps_to_leader >= 1
                and isinstance(leader_lap_diff, (int, float))
                and leader_lap_diff > 50000
            )
            else None
        )
        laps_to_ahead = (
            raw_laps_to_ahead
            if (
                isinstance(raw_laps_to_ahead, int)
                and raw_laps_to_ahead >= 1
                and isinstance(ahead_lap_diff, (int, float))
                and ahead_lap_diff > 50000
            )
            else None
        )

        visible_compound = None
        tyre_age_laps = None
        if isinstance(car_id, int) and 0 <= car_id < len(status_data):
            car_status = status_data[car_id] if isinstance(status_data[car_id], dict) else {}
            visible_compound = _normalize_tyre_compound(
                car_status.get("visualTyreCompoundName") or car_status.get("actualTyreCompoundName")
            )
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
                "gapToLeader": "LEADER"
                if position == 1
                else _format_gap_value(laps_to_leader, leader_lap_diff),
                "gapToAhead": "LEADER"
                if position == 1
                else _format_gap_value(laps_to_ahead, ahead_lap_diff),
                "visibleTyreCompound": visible_compound,
                "tyreAgeLaps": tyre_age_laps,
                "positionChangeSinceStart": _position_change_since_start(
                    position, lap.get("gridPosition")
                ),
                "numberPitStops": lap.get("numPitStops"),
                "unservedPenalties": _unserved_penalties_from_lap(lap),
                "isInPit": bool(is_in_pit),
                "isRetired": _is_retired_status(result_status_name, driver_status_name),
                "isPlayer": bool(row.get("isPlayer")),
            }
        )

    return _strip_nulls(
        {
            "time": _clock_now(),
            "leaderboard": leaderboard,
        }
    )
