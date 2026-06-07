from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.live_data_engine.capture import F1TelemetryCapture


class RaceStateView:
    """Read-only view over the shared telemetry state written by F1TelemetryCapture."""

    def __init__(self, cap: F1TelemetryCapture) -> None:
        self._cap = cap

    # ── Private snapshot helpers ───────────────────────────────────

    def _display_name_from_participants(
        self, participants: list[dict[str, Any]], car_index: int | None
    ) -> str:
        if car_index is None:
            return "Unknown"
        if 0 <= car_index < len(participants):
            participant = participants[car_index]
            return (
                participant.get("displayName")
                or participant.get("driverName")
                or f"Car {car_index}"
            )
        return f"Car {car_index}"

    def _find_car_index_by_name(self, name: str, participants: list[dict[str, Any]]) -> int | None:
        if not name:
            return None
        needle = name.strip().lower()
        if not needle:
            return None
        for participant in participants:
            candidate = (
                participant.get("displayName") or participant.get("driverName") or ""
            ).lower()
            if needle in candidate:
                return participant.get("carIndex")
        return None

    def _collect_penalty_events(
        self, history: list[dict[str, Any]], participants: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        penalties = []
        for entry in history:
            if entry.get("code") != "PENA":
                continue
            details = entry.get("details", {})
            driver_idx = details.get("vehicleIdx")
            penalties.append(
                {
                    "time": entry.get("time"),
                    "driverName": self._display_name_from_participants(participants, driver_idx),
                    "penaltyType": details.get("penaltyTypeName"),
                    "infringementType": details.get("infringementTypeName"),
                    "lapNum": details.get("lapNum"),
                    "placesGained": details.get("placesGained"),
                    "raw": details,
                }
            )
        return penalties

    def _session_snapshot(self) -> dict[str, Any]:
        with self._cap.lock:
            return dict(self._cap.data.get("session", {}))

    def _session_snapshot_with_timestamp(self) -> tuple[dict[str, Any], float]:
        with self._cap.lock:
            return dict(self._cap.data.get("session", {})), self._cap.last_update

    def _lap_participant_snapshot(self) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
        with self._cap.lock:
            return (
                self._cap.player_car_index,
                list(self._cap.data.get("lap_data", {}).get("laps", [])),
                list(self._cap.data.get("participants", {}).get("participants", [])),
            )

    def _car_arrays_with_timestamp(
        self, *pairs: tuple[str, str]
    ) -> tuple[int, list[list[Any]], float]:
        with self._cap.lock:
            idx = self._cap.player_car_index
            arrays = [
                list(self._cap.data.get(category, {}).get(key, [])) for category, key in pairs
            ]
            timestamp = self._cap.last_update
        return idx, arrays, timestamp

    def _car_arrays(self, *pairs: tuple[str, str]) -> tuple[int, list[list[Any]]]:
        idx, arrays, _ = self._car_arrays_with_timestamp(*pairs)
        return idx, arrays

    def _event_history_snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self._cap.lock:
            return (
                list(self._cap.data.get("event", {}).get("eventHistory", [])),
                list(self._cap.data.get("participants", {}).get("participants", [])),
            )

    def _get_car_id_by_position(
        self, laps: list[dict[str, Any]], position: int | None
    ) -> int | None:
        if position is None:
            return None
        for idx, lap in enumerate(laps):
            if lap.get("carPosition") == position:
                return idx
        return None

    # ── Session helpers ────────────────────────────────────────────

    def get_player_presence_state(
        self, stale_after_seconds: float = 3.0, confirm_samples: int = 2
    ) -> dict[str, Any]:
        now = time.time()
        with self._cap.lock:
            session = dict(self._cap.data.get("session", {}))
            lobby = dict(self._cap.data.get("lobby_info", {}))
            laps = list(self._cap.data.get("lap_data", {}).get("laps", []))
            last_update = self._cap.last_update
            last_header = (
                dict(self._cap.last_header) if isinstance(self._cap.last_header, dict) else None
            )
            packet_total = sum(self._cap.packet_counts.values()) + self._cap.unknown_packets
            player_idx = self._cap.player_car_index

        seconds_since_update = max(0.0, now - last_update)
        has_recent_packets = packet_total > 0 and seconds_since_update <= stale_after_seconds

        session_type_name = session.get("sessionTypeName")
        game_mode_name = session.get("gameModeName")
        track_name = session.get("trackName")
        has_session_identity = bool(
            isinstance(session_type_name, str)
            and session_type_name
            and not session_type_name.startswith("Unknown")
        )
        has_game_mode = bool(
            isinstance(game_mode_name, str)
            and game_mode_name
            and not game_mode_name.startswith("Unknown")
        )
        has_track = bool(track_name and track_name not in ("Unknown", "Unknown Track"))

        lobby_players = lobby.get("players")
        if not isinstance(lobby_players, list):
            lobby_players = lobby.get("lobbyPlayers")
        if not isinstance(lobby_players, list):
            lobby_players = []
        lobby_player_count = int(lobby.get("numPlayers") or len(lobby_players))

        has_live_lap_signal = False
        if 0 <= player_idx < len(laps):
            lap = laps[player_idx] if isinstance(laps[player_idx], dict) else {}
            current_lap = lap.get("currentLapNum")
            car_position = lap.get("carPosition")
            has_live_lap_signal = current_lap is not None or (
                isinstance(car_position, int) and car_position > 0
            )

        in_game = (
            has_recent_packets
            and has_session_identity
            and (has_game_mode or has_track or has_live_lap_signal)
        )
        in_lobby = has_recent_packets and not in_game and lobby_player_count > 0
        detected_state = "in_game" if in_game else ("lobby" if in_lobby else "neither")

        detected_reason = "stale_or_no_packets"
        if detected_state == "in_game":
            detected_reason = "session_and_live_signals_present"
        elif detected_state == "lobby":
            detected_reason = "lobby_players_present_without_live_session_signals"

        if confirm_samples < 1:
            confirm_samples = 1

        with self._cap.lock:
            if confirm_samples == 1:
                self._cap._presence_state = detected_state
                self._cap._presence_reason = detected_reason
                self._cap._presence_candidate_state = None
                self._cap._presence_candidate_reason = None
                self._cap._presence_candidate_count = 0
            elif detected_state == self._cap._presence_state:
                self._cap._presence_candidate_state = None
                self._cap._presence_candidate_reason = None
                self._cap._presence_candidate_count = 0
            else:
                if self._cap._presence_candidate_state == detected_state:
                    self._cap._presence_candidate_count += 1
                else:
                    self._cap._presence_candidate_state = detected_state
                    self._cap._presence_candidate_reason = detected_reason
                    self._cap._presence_candidate_count = 1
                if self._cap._presence_candidate_count >= confirm_samples:
                    self._cap._presence_state = detected_state
                    self._cap._presence_reason = detected_reason
                    self._cap._presence_last_transition = now
                    self._cap._presence_candidate_state = None
                    self._cap._presence_candidate_reason = None
                    self._cap._presence_candidate_count = 0

            stable_state = self._cap._presence_state
            stable_reason = self._cap._presence_reason
            candidate_state = self._cap._presence_candidate_state
            candidate_count = self._cap._presence_candidate_count
            last_transition = self._cap._presence_last_transition

        return {
            "state": stable_state,
            "reason": stable_reason,
            "detectedState": detected_state,
            "detectedReason": detected_reason,
            "lastUpdate": last_update,
            "secondsSinceUpdate": round(seconds_since_update, 3),
            "staleAfterSeconds": stale_after_seconds,
            "confirmSamples": confirm_samples,
            "hasRecentPackets": has_recent_packets,
            "packetTotal": packet_total,
            "playerCarIndex": player_idx,
            "sessionTypeName": session_type_name,
            "gameModeName": game_mode_name,
            "trackName": track_name,
            "networkGame": session.get("networkGame"),
            "lobbyPlayerCount": lobby_player_count,
            "pendingTransition": {
                "candidateState": candidate_state,
                "candidateCount": candidate_count,
                "remainingSamples": max(0, confirm_samples - candidate_count)
                if candidate_state
                else 0,
            },
            "lastTransition": last_transition,
            "lastHeader": last_header,
        }

    def get_current_weather(self) -> dict[str, Any]:
        session, last_update = self._session_snapshot_with_timestamp()
        return {
            "weatherName": session.get("weatherName", "Unknown"),
            "trackTemperature": session.get("trackTemperature"),
            "airTemperature": session.get("airTemperature"),
            "lastUpdate": last_update,
        }

    def get_weather_forecast(self) -> dict[str, Any]:
        session = self._session_snapshot()
        forecast_samples = session.get("forecastLatest")
        if forecast_samples is None:
            forecast_samples = session.get("weatherForecast") or []
        if isinstance(forecast_samples, (list, tuple)):
            filtered_samples = []
            for sample in forecast_samples:
                if not isinstance(sample, dict):
                    filtered_samples.append(sample)
                    continue
                is_valid = sample.get("isValidSample")
                if is_valid is False:
                    continue
                filtered_samples.append(sample)
            forecast_samples = filtered_samples
        history = session.get("forecastHistory") or []
        latest_history = history[0] if history else None
        latest_forecast = (
            forecast_samples[0]
            if isinstance(forecast_samples, (list, tuple)) and forecast_samples
            else forecast_samples
        )
        return {
            "latestForecast": latest_forecast,
            "forecastSamples": forecast_samples,
            "forecastHistory": history,
            "latestHistory": latest_history,
        }

    def get_total_laps(self) -> int | None:
        session = self._session_snapshot()
        return session.get("totalLaps")

    def get_current_track(self) -> str:
        session = self._session_snapshot()
        return session.get("trackName") or "Unknown"

    def get_safety_car_status(self) -> str | None:
        session = self._session_snapshot()
        return session.get("safetyCarStatusName")

    def get_pitstop_window_recommendation(self) -> dict[str, int | None]:
        session = self._session_snapshot()
        return {
            "idealLap": session.get("pitStopWindowIdealLap"),
            "latestLap": session.get("pitStopWindowLatestLap"),
        }

    def get_pitstop_rejoin_position(self) -> int | None:
        session = self._session_snapshot()
        return session.get("pitStopRejoinPosition")

    # ── Lap helpers ────────────────────────────────────────────────

    def get_current_lap(self) -> int | None:
        car_index, laps, _ = self._lap_participant_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return lap.get("currentLapNum")

    def get_num_remaining_laps(self) -> int | None:
        car_index, laps, _ = self._lap_participant_snapshot()
        session = self._session_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        current = lap.get("currentLapNum")
        total = session.get("totalLaps")
        if total is None or total <= 0 or current is None:
            return None
        remaining = total - current
        return remaining if remaining >= 0 else 0

    def get_teammate_position(self) -> dict[str, Any] | None:
        player_idx, laps, participants = self._lap_participant_snapshot()
        teammate = next(
            (p for p in participants if p.get("myTeam") and p.get("carIndex") != player_idx),
            None,
        )
        if not teammate:
            return None
        car_idx = teammate.get("carIndex")
        lap = laps[car_idx] if 0 <= car_idx < len(laps) else {}
        return {
            "carIndex": car_idx,
            "driverName": self._display_name_from_participants(participants, car_idx),
            "position": lap.get("carPosition"),
            "currentLap": lap.get("currentLapNum"),
        }

    def get_player_position_by_name(self, name: str) -> dict[str, Any] | None:
        _, laps, participants = self._lap_participant_snapshot()
        car_index = self._find_car_index_by_name(name, participants)
        if car_index is None or car_index >= len(laps):
            return None
        lap = laps[car_index]
        return {
            "carIndex": car_index,
            "driverName": self._display_name_from_participants(participants, car_index),
            "position": lap.get("carPosition"),
            "currentLap": lap.get("currentLapNum"),
        }

    def get_all_grid_positions(self) -> list[dict[str, Any]]:
        _, laps, participants = self._lap_participant_snapshot()
        grid = []
        for idx, lap in enumerate(laps):
            position = lap.get("carPosition")
            if position is None or position == 0:
                continue
            grid.append(
                {
                    "position": position,
                    "driverName": self._display_name_from_participants(participants, idx),
                    "carIndex": idx,
                }
            )
        grid.sort(key=lambda entry: entry["position"] or 999)
        return grid

    def get_safety_car_delta(self) -> float | None:
        car_index, laps, _ = self._lap_participant_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return lap.get("safetyCarDelta")

    def get_player_name_by_position(self, position: int) -> str | None:
        _, laps, participants = self._lap_participant_snapshot()
        car_idx = self._get_car_id_by_position(laps, position)
        if car_idx is None:
            return None
        return self._display_name_from_participants(participants, car_idx)

    # ── Event helpers ──────────────────────────────────────────────

    def get_fastest_lap_data(self) -> dict[str, Any] | None:
        history, participants = self._event_history_snapshot()
        fastest = next((evt for evt in history if evt.get("code") == "FTLP"), None)
        if not fastest:
            return None
        details = fastest.get("details", {})
        driver_idx = details.get("vehicleIdx")
        return {
            "driverName": self._display_name_from_participants(participants, driver_idx),
            "lapTime": details.get("lapTime"),
            "lapTimeFormatted": details.get("lapTimeFormatted"),
            "time": fastest.get("time"),
        }

    def get_drs_status(self) -> dict[str, Any]:
        car_index, arrays = self._car_arrays(
            ("car_telemetry", "carTelemetry"),
            ("car_status", "carStatus"),
        )
        telemetry, status = arrays
        tel = telemetry[car_index] if 0 <= car_index < len(telemetry) else {}
        stat = status[car_index] if 0 <= car_index < len(status) else {}
        return {
            "carIndex": car_index,
            "drsStatus": tel.get("drsStatus"),
            "drsAvailable": stat.get("drsAvailable"),
            "drsFault": stat.get("drsFault"),
        }

    def get_session_info(self) -> dict[str, Any]:
        session, last_update = self._session_snapshot_with_timestamp()
        return {
            "trackName": session.get("trackName", "Unknown"),
            "sessionTypeName": session.get("sessionTypeName", "Unknown"),
            "weatherName": session.get("weatherName", "Clear"),
            "trackTemperature": session.get("trackTemperature", 0),
            "airTemperature": session.get("airTemperature", 0),
            "sessionTimeLeftFormatted": session.get("sessionTimeLeftFormatted", "00:00"),
            "totalLaps": session.get("totalLaps", 0),
            "trackLengthKm": session.get("trackLengthKm", 0),
            "lastUpdate": last_update,
        }

    def get_race_standings(self, limit: int = 22) -> list[dict[str, Any]]:
        standings = []
        player_idx, lap_data, participants = self._lap_participant_snapshot()
        for i in range(min(len(participants), len(lap_data), 22)):
            participant = participants[i]
            lap = lap_data[i]
            if participant.get("displayName") or participant.get("name"):
                driver_info = {
                    "carIndex": i,
                    "position": lap.get("carPosition", 0),
                    "driverName": participant.get(
                        "displayName", participant.get("name", "Unknown")
                    ),
                    "teamName": participant.get("teamName", "Unknown"),
                    "currentLap": lap.get("currentLapNum", 0),
                    "lastLapTime": lap.get("lastLapTimeFormatted", "0:00.000"),
                    "sector1Time": lap.get("sector1TimeFormatted", "00.000"),
                    "sector2Time": lap.get("sector2TimeFormatted", "00.000"),
                    "driverStatus": lap.get("driverStatusName", "Unknown"),
                    "resultStatus": lap.get("resultStatusName", "Unknown"),
                    "isPlayer": i == player_idx,
                    "penalties": lap.get("penaltiesFormatted", "None"),
                    "pitStatus": lap.get("pitStatusName", "None"),
                }
                standings.append(driver_info)
        standings.sort(key=lambda x: x["position"] if x["position"] > 0 else 999)
        return standings[:limit]

    def get_player_telemetry(self) -> dict[str, Any]:
        car_index, arrays, last_update = self._car_arrays_with_timestamp(
            ("car_telemetry", "carTelemetry"),
            ("car_status", "carStatus"),
            ("car_damage", "carDamage"),
        )
        tel_data, status_data, damage_data = arrays

        telemetry = {}
        if tel_data and car_index < len(tel_data):
            tel = tel_data[car_index]
            telemetry = {
                "speedKph": tel.get("speedKph", 0),
                "speedMph": tel.get("speedMph", 0),
                "gear": tel.get("gearDisplay", "N"),
                "engineRPM": tel.get("engineRPM", 0),
                "throttlePercent": tel.get("throttlePercent", 0),
                "brakePercent": tel.get("brakePercent", 0),
                "drsStatus": tel.get("drsStatus", "Off"),
                "engineTemperature": tel.get("engineTemperature", 0),
                "engineTempStatus": tel.get("engineTempStatus", "OK"),
                "tyreTemperatures": {
                    "surface": tel.get("tyresSurfaceTemperature", [0, 0, 0, 0]),
                    "inner": tel.get("tyresInnerTemperature", [0, 0, 0, 0]),
                },
                "brakeTemperatures": tel.get("brakesTemperature", [0, 0, 0, 0]),
                "warnings": {
                    "engine": tel.get("hasEngineWarning", False),
                    "brakes": tel.get("hasBrakeWarning", False),
                    "tyres": tel.get("hasTyreWarning", False),
                },
            }

        status = {}
        if status_data and car_index < len(status_data):
            stat = status_data[car_index]
            status = {
                "fuelPercentage": stat.get("fuelPercentage", 0),
                "fuelRemainingLaps": stat.get("fuelRemainingLaps", 0),
                "fuelMixName": stat.get("fuelMixName", "Standard"),
                "fuelCritical": stat.get("fuelCritical", False),
                "ersPercentage": stat.get("ersPercentage", 0),
                "ersDeployModeName": stat.get("ersDeployModeName", "None"),
                "tyreCompound": stat.get("actualTyreCompoundName", "Unknown"),
                "tyreAge": stat.get("tyresAgeLaps", 0),
                "tyresOld": stat.get("tyresOld", False),
                "drsAvailable": stat.get("drsAvailable", False),
                "flagColor": stat.get("flagColor", "None"),
                "hasYellowFlag": stat.get("hasYellowFlag", False),
                "hasRedFlag": stat.get("hasRedFlag", False),
            }

        damage = {}
        if damage_data and car_index < len(damage_data):
            dmg = damage_data[car_index]
            damage = {
                "tyreWear": dmg.get("m_tyresWear", [0, 0, 0, 0]),
                "frontWingDamage": [
                    dmg.get("m_frontLeftWingDamage", 0),
                    dmg.get("m_frontRightWingDamage", 0),
                ],
                "rearWingDamage": dmg.get("m_rearWingDamage", 0),
                "floorDamage": dmg.get("m_floorDamage", 0),
                "diffuserDamage": dmg.get("m_diffuserDamage", 0),
            }

        return {
            "carIndex": car_index,
            "telemetry": telemetry,
            "status": status,
            "damage": damage,
            "lastUpdate": last_update,
        }

    def get_recent_events(self, limit: int = 5) -> list[dict[str, Any]]:
        events, _ = self._event_history_snapshot()
        return events[:limit]

    def get_driver_by_position(self, position: int) -> dict[str, Any] | None:
        standings = self.get_race_standings()
        return next((d for d in standings if d["position"] == position), None)

    def get_driver_by_name(self, name: str) -> dict[str, Any] | None:
        standings = self.get_race_standings()
        name_lower = name.lower()
        return next((d for d in standings if name_lower in d["driverName"].lower()), None)

    def get_current_position(self) -> dict[str, Any] | None:
        standings = self.get_race_standings()
        return next((s for s in standings if s.get("isPlayer")), None)

    def _gap_to_car(self, target_car_index: int) -> dict[str, Any] | None:
        player_idx, laps, _ = self._lap_participant_snapshot()
        _, telemetry_arrays = self._car_arrays(("car_telemetry", "carTelemetry"))
        tel = telemetry_arrays[0] if telemetry_arrays else []
        if not (0 <= target_car_index < len(laps)) or not (0 <= player_idx < len(laps)):
            return None
        player_lap = laps[player_idx] or {}
        target_lap = laps[target_car_index] or {}
        player_total = player_lap.get("totalDistance", 0) or 0
        target_total = target_lap.get("totalDistance", 0) or 0
        lap_diff = (target_lap.get("currentLapNum") or 0) - (player_lap.get("currentLapNum") or 0)
        gap_meters = target_total - player_total
        try:
            p_speed = (tel[player_idx].get("speedKph") or 0) / 3.6 if player_idx < len(tel) else 0
            t_speed = (
                (tel[target_car_index].get("speedKph") or 0) / 3.6
                if target_car_index < len(tel)
                else 0
            )
            avg_speed = max((p_speed + t_speed) / 2.0, 0.1)
            gap_seconds = gap_meters / avg_speed
            # Discard implausible values caused by totalDistance resetting at lap crossings.
            if abs(gap_seconds) > 180:
                gap_seconds = None
        except Exception:
            gap_seconds = None
        return {
            "targetCarIndex": target_car_index,
            "gapMeters": gap_meters,
            "gapLaps": lap_diff,
            "gapSecondsApprox": gap_seconds,
        }

    def get_gap_to_driver_by_name(self, name: str) -> dict[str, Any] | None:
        driver = self.get_driver_by_name(name)
        if not driver:
            return None
        return self._gap_to_car(driver["carIndex"])

    def get_gap_to_driver_by_position(self, position: int) -> dict[str, Any] | None:
        driver = self.get_driver_by_position(position)
        if not driver:
            return None
        return self._gap_to_car(driver["carIndex"])

    def get_gap_to_driver_in_front(self) -> dict[str, Any] | None:
        player = self.get_current_position()
        if not player:
            return None
        pos = player.get("position")
        if not pos or pos <= 1:
            return None
        return self.get_gap_to_driver_by_position(pos - 1)

    def get_gap_to_driver_in_back(self) -> dict[str, Any] | None:
        player = self.get_current_position()
        if not player:
            return None
        pos = player.get("position")
        if not pos:
            return None
        return self.get_gap_to_driver_by_position(pos + 1)

    def get_fuel_status(self) -> dict[str, Any]:
        car_index, arrays = self._car_arrays(("car_status", "carStatus"))
        status_data = arrays[0]
        status = status_data[car_index] if car_index < len(status_data) else {}
        return {
            "carIndex": car_index,
            "fuelPercentage": status.get("fuelPercentage"),
            "fuelRemainingLaps": status.get("fuelRemainingLaps"),
            "fuelMixName": status.get("fuelMixName"),
            "fuelCritical": status.get("fuelCritical"),
        }

    def get_ers_status(self) -> dict[str, Any]:
        car_index, arrays = self._car_arrays(("car_status", "carStatus"))
        status_data = arrays[0]
        status = status_data[car_index] if car_index < len(status_data) else {}
        return {
            "carIndex": car_index,
            "ersPercentage": status.get("ersPercentage"),
            "ersDeployModeName": status.get("ersDeployModeName"),
        }

    def get_tyres_status(self) -> dict[str, Any]:
        car_index, arrays = self._car_arrays(
            ("car_status", "carStatus"),
            ("car_telemetry", "carTelemetry"),
            ("car_damage", "carDamage"),
        )
        status_data, tel_data, dmg_data = arrays
        status = status_data[car_index] if car_index < len(status_data) else {}
        tel = tel_data[car_index] if car_index < len(tel_data) else {}
        dmg = dmg_data[car_index] if car_index < len(dmg_data) else {}
        return {
            "carIndex": car_index,
            "compound": status.get("visualTyreCompoundName")
            or status.get("actualTyreCompoundName"),
            "ageLaps": status.get("tyresAgeLaps"),
            "tyresOld": status.get("tyresOld"),
            "surfaceTemp": tel.get("tyresSurfaceTemperature"),
            "innerTemp": tel.get("tyresInnerTemperature"),
            "pressures": tel.get("tyresPressure"),
            "wear": dmg.get("m_tyresWear"),
        }

    def get_damage_status(self) -> dict[str, Any]:
        car_index, arrays = self._car_arrays(("car_damage", "carDamage"))
        dmg_data = arrays[0]
        dmg = dmg_data[car_index] if car_index < len(dmg_data) else {}
        return {
            "carIndex": car_index,
            "tyreWear": dmg.get("m_tyresWear"),
            "frontWingDamage": [
                dmg.get("m_frontLeftWingDamage"),
                dmg.get("m_frontRightWingDamage"),
            ],
            "rearWingDamage": dmg.get("m_rearWingDamage"),
            "floorDamage": dmg.get("m_floorDamage"),
            "diffuserDamage": dmg.get("m_diffuserDamage"),
            "drsFault": dmg.get("m_drsFault"),
        }

    def get_capture_stats(self) -> dict[str, Any]:
        with self._cap.lock:
            counts = dict(self._cap.packet_counts)
            unknown = self._cap.unknown_packets
            errors = self._cap.error_count
            last_hdr = (
                dict(self._cap.last_header) if isinstance(self._cap.last_header, dict) else None
            )
            last_err = self._cap.last_error
        return {
            "packetCounts": counts,
            "unknownPackets": unknown,
            "errors": errors,
            "lastHeader": last_hdr,
            "lastError": last_err,
            "formatMismatch": self._cap.format_mismatch,
        }

    def get_motion_ex(self) -> dict[str, Any]:
        with self._cap.lock:
            return dict(self._cap.data.get("motion_ex") or {})

    def get_tyre_sets(self) -> dict[str, Any] | None:
        with self._cap.lock:
            return self._cap.data.get("tyre_sets", {}).get("latest")

    def get_time_trial_data(self) -> dict[str, Any]:
        with self._cap.lock:
            return dict(self._cap.data.get("time_trial") or {})

    def get_lap_positions(self) -> dict[str, Any]:
        with self._cap.lock:
            return dict(self._cap.data.get("lap_positions") or {})

    def get_car_telemetry_history(self, car_index: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._cap.lock:
            dq = []
            if 0 <= car_index < len(self._cap.car_history.car_telemetry):
                dq = list(self._cap.car_history.car_telemetry[car_index])
        return list(reversed(dq[-limit:]))

    def get_car_status_changes(self, car_index: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._cap.lock:
            dq = []
            if 0 <= car_index < len(self._cap.car_history.car_status):
                dq = list(self._cap.car_history.car_status[car_index])
        return list(reversed(dq[-limit:]))

    def get_car_damage_events(self, car_index: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._cap.lock:
            dq = []
            if 0 <= car_index < len(self._cap.car_history.car_damage):
                dq = list(self._cap.car_history.car_damage[car_index])
        return list(reversed(dq[-limit:]))

    def get_car_lap_history(self, car_index: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._cap.lock:
            laps = self._cap.data.get("lap_data", {}).get("history", [])
            entries = laps[car_index] if 0 <= car_index < len(laps) else []
        return entries[:limit]

    def get_session_changes(self, limit: int = 50) -> list[dict[str, Any]]:
        session = self._session_snapshot()
        changes = session.get("changes", [])
        return changes[:limit]

    def get_session_forecast(self, limit: int = 10) -> dict[str, Any]:
        session = self._session_snapshot()
        latest = session.get("forecastLatest")
        history = session.get("forecastHistory") or []
        return {"latest": latest, "history": history[:limit]}

    def get_safety_periods(self) -> list[dict[str, Any]]:
        session = self._session_snapshot()
        return session.get("safetyPeriods", [])
