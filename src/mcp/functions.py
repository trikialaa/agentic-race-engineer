from __future__ import annotations

from typing import Dict, Any, List, Optional

from src.live_data_engine.capture import F1TelemetryCapture


def get_session_info(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_session_info()


def get_current_weather(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_current_weather()


def get_weather_forecast(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_weather_forecast()


def get_total_laps(capture: F1TelemetryCapture) -> Optional[int]:
    return capture.get_total_laps()


def get_current_track(capture: F1TelemetryCapture) -> str:
    return capture.get_current_track()


def get_safety_car_status(capture: F1TelemetryCapture) -> Optional[str]:
    return capture.get_safety_car_status()


def get_pitstop_window_recommendation(capture: F1TelemetryCapture) -> Dict[str, Optional[int]]:
    return capture.get_pitstop_window_recommendation()


def get_pitstop_rejoin_position(capture: F1TelemetryCapture) -> Optional[int]:
    return capture.get_pitstop_rejoin_position()


def get_race_standings(capture: F1TelemetryCapture, limit: int = 22) -> List[Dict[str, Any]]:
    return capture.get_race_standings(limit)


def get_player_telemetry(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_player_telemetry()


def get_recent_events(capture: F1TelemetryCapture, limit: int = 5) -> List[Dict[str, Any]]:
    return capture.get_recent_events(limit)


def get_current_lap(capture: F1TelemetryCapture) -> Optional[int]:
    return capture.get_current_lap()


def get_num_remaining_laps(capture: F1TelemetryCapture) -> Optional[int]:
    return capture.get_num_remaining_laps()


def get_penalties(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_penalties()


def get_penalties_by_player(capture: F1TelemetryCapture, name: str) -> Optional[Dict[str, Any]]:
    return capture.get_penalties_by_player(name)


def get_teammate_position(capture: F1TelemetryCapture) -> Optional[Dict[str, Any]]:
    return capture.get_teammate_position()


def get_player_position_by_name(capture: F1TelemetryCapture, name: str) -> Optional[Dict[str, Any]]:
    return capture.get_player_position_by_name(name)


def get_all_grid_positions(capture: F1TelemetryCapture) -> List[Dict[str, Any]]:
    return capture.get_all_grid_positions()


def get_safety_car_delta(capture: F1TelemetryCapture) -> Optional[float]:
    return capture.get_safety_car_delta()


def get_player_name_by_position(capture: F1TelemetryCapture, position: int) -> Optional[str]:
    return capture.get_player_name_by_position(position)


def get_fastest_lap_data(capture: F1TelemetryCapture) -> Optional[Dict[str, Any]]:
    return capture.get_fastest_lap_data()


def get_penalities(capture: F1TelemetryCapture) -> List[Dict[str, Any]]:
    return capture.get_penalities()


def get_penalities_by_driver_name(capture: F1TelemetryCapture, name: str) -> List[Dict[str, Any]]:
    return capture.get_penalities_by_driver_name(name)


def get_drs_status(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_drs_status()


def get_driver_by_position(capture: F1TelemetryCapture, position: int) -> Optional[Dict[str, Any]]:
    return capture.get_driver_by_position(position)


def get_driver_by_name(capture: F1TelemetryCapture, name: str) -> Optional[Dict[str, Any]]:
    return capture.get_driver_by_name(name)


def get_top_drivers(capture: F1TelemetryCapture, count: int = 5) -> List[Dict[str, Any]]:
    return capture.get_top_drivers(count)


def get_race_summary(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_race_summary()


def get_capture_stats(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_capture_stats()


def get_current_position(capture: F1TelemetryCapture) -> Optional[Dict[str, Any]]:
    return capture.get_current_position()


def get_gap_to_driver_by_name(capture: F1TelemetryCapture, name: str) -> Optional[Dict[str, Any]]:
    return capture.get_gap_to_driver_by_name(name)


def get_gap_to_driver_by_position(capture: F1TelemetryCapture, position: int) -> Optional[Dict[str, Any]]:
    return capture.get_gap_to_driver_by_position(position)


def get_gap_to_driver_in_front(capture: F1TelemetryCapture) -> Optional[Dict[str, Any]]:
    return capture.get_gap_to_driver_in_front()


def get_gap_to_driver_in_back(capture: F1TelemetryCapture) -> Optional[Dict[str, Any]]:
    return capture.get_gap_to_driver_in_back()


def get_fuel_status(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_fuel_status()


def get_ers_status(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_ers_status()


def get_tyres_status(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_tyres_status()


def get_damage_status(capture: F1TelemetryCapture) -> Dict[str, Any]:
    return capture.get_damage_status()


def get_car_telemetry_history(capture: F1TelemetryCapture, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    return capture.get_car_telemetry_history(car_index, limit)


def get_car_status_changes(capture: F1TelemetryCapture, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    return capture.get_car_status_changes(car_index, limit)


def get_car_damage_events(capture: F1TelemetryCapture, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    return capture.get_car_damage_events(car_index, limit)


def get_car_lap_history(capture: F1TelemetryCapture, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    return capture.get_car_lap_history(car_index, limit)


def get_session_changes(capture: F1TelemetryCapture, limit: int = 50) -> List[Dict[str, Any]]:
    return capture.get_session_changes(limit)


def get_session_forecast(capture: F1TelemetryCapture, limit: int = 10) -> Dict[str, Any]:
    return capture.get_session_forecast(limit)


def get_safety_periods(capture: F1TelemetryCapture) -> List[Dict[str, Any]]:
    return capture.get_safety_periods()
