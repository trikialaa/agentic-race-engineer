from __future__ import annotations

from typing import Any

from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.functions._shared import _clock_now, _strip_nulls


def get_weather_forecast(capture: F1TelemetryCapture) -> dict[str, Any]:
    weather_now = capture.query.get_current_weather()
    forecast = capture.query.get_weather_forecast()
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
        if (
            offset is None
            and weather_name is None
            and rain_pct is None
            and track_temp is None
            and air_temp is None
        ):
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

    return _strip_nulls(
        {
            "time": _clock_now(),
            "current": {
                "weather": weather_now.get("weatherName"),
                "trackTempC": weather_now.get("trackTemperature"),
                "airTempC": weather_now.get("airTemperature"),
            },
            "forecast": detailed_forecast,
        }
    )
