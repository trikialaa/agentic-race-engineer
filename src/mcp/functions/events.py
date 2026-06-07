from __future__ import annotations

import time
from typing import Any, Dict, List

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.functions._shared import _clock_now, _normalize_tyre_compound, _strip_nulls
from src.udp_parser.constants import VISUAL_TYRE_COMPOUNDS


def get_recent_events(capture: F1TelemetryCapture) -> Dict[str, Any]:
    with capture.lock:
        stream = list(capture.classified_event_stream)
    return {
        "events": stream[:60],
        "serverTime": time.time(),
    }


def get_strategy(capture: F1TelemetryCapture) -> Dict[str, Any]:
    pit_window = capture.query.get_pitstop_window_recommendation()
    rejoin_pos_raw = capture.query.get_pitstop_rejoin_position()
    rejoin_pos = rejoin_pos_raw if isinstance(rejoin_pos_raw, int) and rejoin_pos_raw > 0 else None
    tyre_sets_data = capture.query.get_tyre_sets()
    tyres = capture.query.get_tyres_status()
    current_lap = capture.query.get_current_lap()

    ideal_lap = pit_window.get("idealLap") or None
    latest_lap = pit_window.get("latestLap") or None
    laps_until_ideal = (
        (ideal_lap - current_lap)
        if isinstance(ideal_lap, int) and ideal_lap > 0 and isinstance(current_lap, int)
        else None
    )

    available_sets: List[Dict[str, Any]] = []
    if isinstance(tyre_sets_data, dict):
        for s in tyre_sets_data.get("tyreSets", []):
            if not isinstance(s, dict) or not s.get("available"):
                continue
            compound_id = s.get("visualTyreCompound")
            compound = _normalize_tyre_compound(
                VISUAL_TYRE_COMPOUNDS.get(compound_id) if isinstance(compound_id, int) else None
            )
            wear = s.get("wear")
            lap_delta_ms = s.get("lapDeltaTime")
            available_sets.append({
                "compound": compound,
                "wear": wear,
                "isNew": isinstance(wear, int) and wear == 0,
                "isFitted": bool(s.get("isFitted")),
                "lapDeltaMs": lap_delta_ms,
            })

    return _strip_nulls({
        "time": _clock_now(),
        "pitWindow": {
            "idealLap": ideal_lap,
            "latestLap": latest_lap,
            "lapsUntilIdeal": laps_until_ideal,
        },
        "rejoinPosition": rejoin_pos,
        "currentTyre": {
            "compound": _normalize_tyre_compound(tyres.get("compound")),
            "ageLaps": tyres.get("ageLaps"),
        },
        "availableSets": available_sets,
    })
