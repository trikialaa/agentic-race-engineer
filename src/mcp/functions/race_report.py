from __future__ import annotations

from typing import Any

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.functions._shared import _strip_nulls, _clock_now

VISUAL_COMPOUND = {16: "Soft", 17: "Medium", 18: "Hard", 7: "Inter", 8: "Wet"}


def _fmt_ms(ms: int | None) -> str | None:
    if not isinstance(ms, int) or ms <= 0:
        return None
    total_s = ms / 1000.0
    mins = int(total_s // 60)
    secs = total_s - mins * 60
    return f"{mins}:{secs:06.3f}"


def get_race_report(capture: F1TelemetryCapture) -> dict[str, Any]:
    final = capture.query.get_final_classification()
    participants = capture.data.get("participants", {}).get("participants", []) or []
    player_idx = capture.player_car_index

    # Build name/team lookup by car index
    driver_info: dict[int, dict] = {}
    for i, p in enumerate(participants):
        if isinstance(p, dict):
            driver_info[i] = {
                "name": p.get("name") or p.get("driverName") or f"Car {i}",
                "team": p.get("teamName") or "",
            }

    entries: list[dict] = []
    if final and isinstance(final.get("classificationData"), list):
        num_cars = final.get("numCars", 22)
        for i, c in enumerate(final["classificationData"][:num_cars]):
            if not isinstance(c, dict):
                continue
            pos = c.get("position", 0)
            if pos <= 0:
                continue
            grid = c.get("gridPosition", 0)
            pos_change = (grid - pos) if grid > 0 and pos > 0 else None
            stints_actual = c.get("tyreStintsActual") or []
            stints_visual = c.get("tyreStintsVisual") or []
            stints_end = c.get("tyreStintsEndLaps") or []
            num_stints = c.get("numTyreStints", 0)
            tyre_stints = []
            for s in range(min(num_stints, len(stints_visual))):
                compound = VISUAL_COMPOUND.get(stints_visual[s], f"#{stints_visual[s]}")
                end_lap = stints_end[s] if s < len(stints_end) else None
                tyre_stints.append({"compound": compound, "endLap": end_lap if end_lap != 255 else None})
            info = driver_info.get(i, {"name": f"Car {i}", "team": ""})
            entries.append(_strip_nulls({
                "position": pos,
                "gridPosition": grid if grid > 0 else None,
                "positionChange": pos_change,
                "isPlayer": i == player_idx,
                "name": info["name"],
                "team": info["team"],
                "numLaps": c.get("numLaps"),
                "numPitStops": c.get("numPitStops"),
                "bestLapTime": _fmt_ms(c.get("bestLapTimeInMS")),
                "totalRaceTime": round(c.get("totalRaceTime", 0), 3) or None,
                "penaltiesTime": c.get("penaltiesTime") or None,
                "numPenalties": c.get("numPenalties") or None,
                "resultStatus": c.get("resultReasonName"),
                "tyreStints": tyre_stints or None,
            }))
        entries.sort(key=lambda e: e.get("position", 999))

    # Notable events for the report (FTLP, PENA, RTMT filtered from event stream)
    report_codes = {"FTLP", "PENA", "RTMT", "RCWN"}
    events = list(capture.classified_event_stream)
    notable = []
    for ev in reversed(events):
        if ev.get("code") in report_codes:
            notable.append({
                "code": ev["code"],
                "eventName": ev.get("eventName", ""),
                "time": ev.get("time"),
                "involvesPlayer": ev.get("involvesPlayer", False),
                "details": ev.get("details") or {},
            })

    return _strip_nulls({
        "time": _clock_now(),
        "available": bool(entries),
        "results": entries if entries else None,
        "notableEvents": notable if notable else None,
    })
