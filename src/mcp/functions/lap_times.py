from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.functions._shared import _clock_now, _strip_nulls

_LAP_TIMES_STATE: Dict[int, Dict[str, Dict[str, Optional[str]]]] = {}
_LAP_TIMES_SESSION_UID: Optional[Any] = None


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


def get_lap_times(capture: F1TelemetryCapture) -> Dict[str, Any]:
    global _LAP_TIMES_SESSION_UID
    current_uid = (capture.last_header or {}).get("sessionUID")
    if current_uid is not None and current_uid != _LAP_TIMES_SESSION_UID:
        _LAP_TIMES_STATE.clear()
        _LAP_TIMES_SESSION_UID = current_uid

    with capture.lock:
        session_history_by_car = list(getattr(capture, "session_history_by_car", []))
    standings = capture.query.get_race_standings(limit=22)
    _, lap_data, _ = capture.query._lap_participant_snapshot()
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

        rows.append({
            "position": position,
            "carId": car_id,
            "driver": row.get("driverName"),
            "mostRecent": most_recent_out,
            "best": best_out,
        })

    return _strip_nulls({
        "time": _clock_now(),
        "lapTimes": rows,
    })
