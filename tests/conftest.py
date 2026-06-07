"""pytest configuration: autouse fixtures for deterministic isolation."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_lap_times_state():
    """Clear the module-level lap-times accumulator before every test."""
    from tests.helpers import reset_lap_times_state

    reset_lap_times_state()
    yield
    reset_lap_times_state()


@pytest.fixture(autouse=True)
def _pin_buffer_env(monkeypatch):
    """Pin F1_BUFFER_* env vars to defaults so ringbuffer depths are reproducible."""
    defaults = {
        "F1_BUFFER_CAR_TELEMETRY": "120",
        "F1_BUFFER_CAR_STATUS": "100",
        "F1_BUFFER_CAR_DAMAGE": "100",
        "F1_BUFFER_LAP_EVENTS": "200",
        "F1_BUFFER_CAR_SETUPS": "20",
        "F1_BUFFER_SESSION": "200",
        "F1_BUFFER_FORECAST": "50",
        "F1_BUFFER_MARSHAL": "200",
        "F1_BUFFER_MOTION_LAPS": "5",
        "F1_BUFFER_MOTION_SAMPLES": "300",
        "F1_BUFFER_LAP_HISTORY": "50",
        "F1_BUFFER_POSITION_CHANGES": "200",
        "F1_BUFFER_PIT_EVENTS": "100",
        "F1_EVENTS_BUFFER": "100",
    }
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)
