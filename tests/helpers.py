"""Shared test utilities: in-process fixture loader and output masker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.live_data_engine.fixture_replay import replay_fixture_into

FIXTURE_BIN = Path(__file__).parent / "fixtures" / "race_catalunya_2025.bin"
MARKERS_JSON = Path(__file__).parent / "fixtures" / "markers.json"
GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"

_MASK_KEYS = frozenset({"time", "serverTime", "ts", "mode"})


def mask(obj: Any) -> Any:
    """Recursively strip wall-clock and transient fields before golden compare."""
    if isinstance(obj, dict):
        return {k: mask(v) for k, v in obj.items() if k not in _MASK_KEYS}
    if isinstance(obj, list):
        return [mask(v) for v in obj]
    return obj


def load_markers() -> dict[str, int]:
    return json.loads(MARKERS_JSON.read_text())


def load_capture_to(frame: int | None = None, bin_path: Path = FIXTURE_BIN):
    """Return an F1TelemetryCapture fed with fixture packets up to `frame` (inclusive).

    No UDP socket or thread started — feeds through the same production
    decode+_update_data path the socket loop uses.
    """
    from src.live_data_engine.capture import F1TelemetryCapture

    cap = F1TelemetryCapture()
    replay_fixture_into(cap, bin_path, frame=frame)
    return cap


def load_golden(tool: str, scenario: str) -> Any:
    path = GOLDEN_DIR / f"{tool}__{scenario}.json"
    return json.loads(path.read_text())


def reset_lap_times_state() -> None:
    import src.mcp.functions.lap_times as lt

    lt._LAP_TIMES_STATE.clear()
    lt._LAP_TIMES_SESSION_UID = None
