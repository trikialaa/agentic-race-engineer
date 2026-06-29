"""Unit tests for live_data_engine/query.py.

Uses a real F1TelemetryCapture (no socket started) with synthetic data injected
directly into cap.data.  No API keys, no game, no UDP socket required.
"""

from __future__ import annotations

import time

from src.live_data_engine.capture import F1TelemetryCapture
from src.live_data_engine.query import RaceStateView


# ── minimal capture factory ───────────────────────────────────────────────────


def _cap(
    player_idx: int = 0,
    laps: list | None = None,
    participants: list | None = None,
    session: dict | None = None,
    car_telemetry: list | None = None,
    car_status: list | None = None,
    car_damage: list | None = None,
    events: list | None = None,
) -> F1TelemetryCapture:
    cap = F1TelemetryCapture()
    cap.player_car_index = player_idx
    if laps is not None:
        cap.data["lap_data"]["laps"] = laps
    if participants is not None:
        cap.data["participants"]["participants"] = participants
    if session is not None:
        cap.data["session"] = session
    if car_telemetry is not None:
        cap.data["car_telemetry"]["carTelemetry"] = car_telemetry
    if car_status is not None:
        cap.data["car_status"]["carStatus"] = car_status
    if car_damage is not None:
        cap.data["car_damage"]["carDamage"] = car_damage
    if events is not None:
        cap.data["event"]["eventHistory"] = events
    return cap


# ── _display_name_from_participants ──────────────────────────────────────────


class TestDisplayNameFromParticipants:
    def _view(self, participants, car_index):
        cap = _cap(participants=participants)
        return RaceStateView(cap)._display_name_from_participants(participants, car_index)

    def test_none_car_index_returns_unknown(self):
        assert self._view([], None) == "Unknown"

    def test_out_of_range_returns_car_n(self):
        assert self._view([], 5) == "Car 5"

    def test_display_name_preferred(self):
        p = [{"displayName": "HAM", "driverName": "Hamilton", "carIndex": 0}]
        assert self._view(p, 0) == "HAM"

    def test_driver_name_fallback(self):
        p = [{"driverName": "Hamilton", "carIndex": 0}]
        assert self._view(p, 0) == "Hamilton"

    def test_car_n_fallback(self):
        p = [{"carIndex": 0}]
        assert self._view(p, 0) == "Car 0"


# ── _find_car_index_by_name ───────────────────────────────────────────────────


class TestFindCarIndexByName:
    def _view(self, participants, name):
        cap = _cap(participants=participants)
        return RaceStateView(cap)._find_car_index_by_name(name, participants)

    def test_empty_name_returns_none(self):
        assert self._view([], "") is None

    def test_whitespace_only_returns_none(self):
        assert self._view([], "   ") is None

    def test_partial_match(self):
        p = [{"displayName": "Lewis Hamilton", "carIndex": 7}]
        assert self._view(p, "hamilton") == 7

    def test_no_match_returns_none(self):
        p = [{"displayName": "Hamilton", "carIndex": 7}]
        assert self._view(p, "verstappen") is None

    def test_case_insensitive(self):
        p = [{"driverName": "HAMILTON", "carIndex": 3}]
        assert self._view(p, "hamilton") == 3


# ── _collect_penalty_events ───────────────────────────────────────────────────


class TestCollectPenaltyEvents:
    def _collect(self, history, participants):
        cap = _cap(participants=participants)
        return RaceStateView(cap)._collect_penalty_events(history, participants)

    def test_non_pena_events_excluded(self):
        history = [{"code": "COLL", "details": {}}]
        result = self._collect(history, [])
        assert result == []

    def test_pena_event_included(self):
        participants = [{"displayName": "Hamilton", "carIndex": 0}]
        history = [
            {
                "code": "PENA",
                "time": "12:00",
                "details": {
                    "vehicleIdx": 0,
                    "penaltyTypeName": "5s Time Penalty",
                    "infringementTypeName": "Corner cutting",
                    "lapNum": 10,
                    "placesGained": None,
                },
            }
        ]
        result = self._collect(history, participants)
        assert len(result) == 1
        assert result[0]["penaltyType"] == "5s Time Penalty"
        assert result[0]["driverName"] == "Hamilton"

    def test_multiple_pena_events(self):
        history = [
            {"code": "PENA", "time": "12:00", "details": {"vehicleIdx": 0}},
            {"code": "PENA", "time": "12:01", "details": {"vehicleIdx": 1}},
        ]
        result = self._collect(history, [])
        assert len(result) == 2


# ── _get_car_id_by_position ───────────────────────────────────────────────────


class TestGetCarIdByPosition:
    def _get(self, laps, position):
        cap = _cap(laps=laps)
        return RaceStateView(cap)._get_car_id_by_position(laps, position)

    def test_none_position_returns_none(self):
        assert self._get([{"carPosition": 1}], None) is None

    def test_match_returns_index(self):
        laps = [{"carPosition": 3}, {"carPosition": 1}]
        assert self._get(laps, 1) == 1

    def test_no_match_returns_none(self):
        laps = [{"carPosition": 2}]
        assert self._get(laps, 5) is None


# ── get_fastest_lap_data ──────────────────────────────────────────────────────


class TestGetFastestLapData:
    def test_no_events_returns_none(self):
        cap = _cap(events=[])
        result = RaceStateView(cap).get_fastest_lap_data()
        assert result is None

    def test_no_ftlp_event_returns_none(self):
        cap = _cap(events=[{"code": "COLL", "details": {}}])
        result = RaceStateView(cap).get_fastest_lap_data()
        assert result is None

    def test_ftlp_event_returns_data(self):
        cap = _cap(
            participants=[{"displayName": "Hamilton", "carIndex": 0}],
            events=[
                {
                    "code": "FTLP",
                    "time": "12:00",
                    "details": {"vehicleIdx": 0, "lapTime": 83962, "lapTimeFormatted": "1:23.962"},
                }
            ],
        )
        result = RaceStateView(cap).get_fastest_lap_data()
        assert result is not None
        assert result["lapTimeFormatted"] == "1:23.962"
        assert result["driverName"] == "Hamilton"


# ── get_drs_status ────────────────────────────────────────────────────────────


class TestGetDrsStatus:
    def test_empty_data_returns_empty_dicts(self):
        cap = _cap()
        result = RaceStateView(cap).get_drs_status()
        assert "carIndex" in result
        assert "drsStatus" in result

    def test_drs_status_from_telemetry(self):
        cap = _cap(
            player_idx=0,
            car_telemetry=[{"drsStatus": "Open"}],
            car_status=[{"drsAvailable": True, "drsFault": False}],
        )
        result = RaceStateView(cap).get_drs_status()
        assert result["drsStatus"] == "Open"
        assert result["drsAvailable"] is True


# ── get_teammate_position ─────────────────────────────────────────────────────


class TestGetTeammatePosition:
    def test_no_teammate_returns_none(self):
        cap = _cap(
            player_idx=0,
            participants=[{"carIndex": 0, "displayName": "Player", "myTeam": False}],
        )
        result = RaceStateView(cap).get_teammate_position()
        assert result is None

    def test_teammate_found(self):
        cap = _cap(
            player_idx=0,
            participants=[
                {"carIndex": 0, "displayName": "Player", "myTeam": False},
                {"carIndex": 1, "displayName": "Teammate", "myTeam": True},
            ],
            laps=[{"carPosition": 1, "currentLapNum": 5}, {"carPosition": 3, "currentLapNum": 5}],
        )
        result = RaceStateView(cap).get_teammate_position()
        assert result is not None
        assert result["carIndex"] == 1
        assert result["position"] == 3


# ── get_all_grid_positions ────────────────────────────────────────────────────


class TestGetAllGridPositions:
    def test_empty_laps(self):
        cap = _cap()
        result = RaceStateView(cap).get_all_grid_positions()
        assert result == []

    def test_zero_position_excluded(self):
        cap = _cap(laps=[{"carPosition": 0}, {"carPosition": 1}])
        result = RaceStateView(cap).get_all_grid_positions()
        assert len(result) == 1
        assert result[0]["position"] == 1

    def test_sorted_by_position(self):
        cap = _cap(
            laps=[{"carPosition": 3}, {"carPosition": 1}, {"carPosition": 2}],
            participants=[
                {"displayName": "A", "carIndex": 0},
                {"displayName": "B", "carIndex": 1},
                {"displayName": "C", "carIndex": 2},
            ],
        )
        result = RaceStateView(cap).get_all_grid_positions()
        positions = [r["position"] for r in result]
        assert positions == [1, 2, 3]


# ── get_player_name_by_position ───────────────────────────────────────────────


class TestGetPlayerNameByPosition:
    def test_no_match_returns_none(self):
        cap = _cap(laps=[{"carPosition": 1}])
        result = RaceStateView(cap).get_player_name_by_position(99)
        assert result is None

    def test_finds_driver_at_position(self):
        cap = _cap(
            laps=[{"carPosition": 2}],
            participants=[{"displayName": "Max", "carIndex": 0}],
        )
        result = RaceStateView(cap).get_player_name_by_position(2)
        assert result == "Max"


# ── get_player_position_by_name ───────────────────────────────────────────────


class TestGetPlayerPositionByName:
    def test_no_match_returns_none(self):
        cap = _cap(participants=[{"displayName": "Hamilton", "carIndex": 0}])
        result = RaceStateView(cap).get_player_position_by_name("Verstappen")
        assert result is None

    def test_found_returns_data(self):
        cap = _cap(
            participants=[{"displayName": "Hamilton", "carIndex": 0}],
            laps=[{"carPosition": 1, "currentLapNum": 10}],
        )
        result = RaceStateView(cap).get_player_position_by_name("hamilton")
        assert result is not None
        assert result["carIndex"] == 0
        assert result["position"] == 1


# ── get_num_remaining_laps ────────────────────────────────────────────────────


class TestGetNumRemainingLaps:
    def test_no_session_data(self):
        cap = _cap()
        assert RaceStateView(cap).get_num_remaining_laps() is None

    def test_calculates_remaining(self):
        cap = _cap(
            session={"totalLaps": 66},
            laps=[{"currentLapNum": 30}],
        )
        assert RaceStateView(cap).get_num_remaining_laps() == 36

    def test_zero_total_laps_returns_none(self):
        cap = _cap(session={"totalLaps": 0}, laps=[{"currentLapNum": 5}])
        assert RaceStateView(cap).get_num_remaining_laps() is None


# ── gap methods ───────────────────────────────────────────────────────────────


class TestGapMethods:
    def _cap_with_two_cars(self, player_pos, rival_pos, player_dist, rival_dist,
                            player_speed_kph=100, rival_speed_kph=100):
        laps = [
            {"carPosition": player_pos, "totalDistance": player_dist, "currentLapNum": 1},
            {"carPosition": rival_pos, "totalDistance": rival_dist, "currentLapNum": 1},
        ]
        tel = [
            {"speedKph": player_speed_kph},
            {"speedKph": rival_speed_kph},
        ]
        participants = [
            {"displayName": "Player", "carIndex": 0},
            {"displayName": "Rival", "carIndex": 1},
        ]
        return _cap(player_idx=0, laps=laps, car_telemetry=tel, participants=participants)

    def test_gap_to_driver_in_front_none_if_p1(self):
        laps = [{"carPosition": 1, "totalDistance": 1000, "currentLapNum": 1}]
        participants = [{"displayName": "Player", "carIndex": 0}]
        cap = _cap(player_idx=0, laps=laps, participants=participants)
        result = RaceStateView(cap).get_gap_to_driver_in_front()
        assert result is None

    def test_gap_to_driver_by_name_not_found(self):
        cap = _cap()
        result = RaceStateView(cap).get_gap_to_driver_by_name("Nonexistent")
        assert result is None

    def test_gap_to_driver_by_position_not_found(self):
        cap = _cap()
        result = RaceStateView(cap).get_gap_to_driver_by_position(99)
        assert result is None

    def test_gap_to_car_returns_gap_data(self):
        cap = self._cap_with_two_cars(
            player_pos=2, rival_pos=1,
            player_dist=1000, rival_dist=1100,
        )
        view = RaceStateView(cap)
        result = view._gap_to_car(1)
        assert result is not None
        assert result["targetCarIndex"] == 1
        assert result["gapMeters"] == 100

    def test_gap_seconds_implausible_returns_none(self):
        # Gap > 180s in seconds is discarded
        cap = self._cap_with_two_cars(
            player_pos=2, rival_pos=1,
            player_dist=0, rival_dist=999999,
            player_speed_kph=1, rival_speed_kph=1,
        )
        result = RaceStateView(cap)._gap_to_car(1)
        assert result is not None
        assert result["gapSecondsApprox"] is None


# ── history/stats methods ─────────────────────────────────────────────────────


class TestHistoryMethods:
    def test_get_car_telemetry_history_empty(self):
        cap = _cap()
        result = RaceStateView(cap).get_car_telemetry_history(0)
        assert result == []

    def test_get_car_status_changes_empty(self):
        cap = _cap()
        result = RaceStateView(cap).get_car_status_changes(0)
        assert result == []

    def test_get_car_damage_events_empty(self):
        cap = _cap()
        result = RaceStateView(cap).get_car_damage_events(0)
        assert result == []

    def test_get_car_lap_history_empty(self):
        cap = _cap()
        result = RaceStateView(cap).get_car_lap_history(0)
        assert result == []

    def test_get_session_changes_empty(self):
        cap = _cap()
        result = RaceStateView(cap).get_session_changes()
        assert result == []

    def test_get_final_classification_none(self):
        cap = _cap()
        result = RaceStateView(cap).get_final_classification()
        assert result is None

    def test_get_capture_stats_shape(self):
        cap = _cap()
        result = RaceStateView(cap).get_capture_stats()
        assert "packetCounts" in result
        assert "errors" in result

    def test_get_tyre_sets_none_default(self):
        cap = _cap()
        result = RaceStateView(cap).get_tyre_sets()
        assert result is None

    def test_get_motion_ex_empty(self):
        cap = _cap()
        result = RaceStateView(cap).get_motion_ex()
        assert isinstance(result, dict)

    def test_get_safety_periods_empty(self):
        cap = _cap(session={"safetyPeriods": []})
        result = RaceStateView(cap).get_safety_periods()
        assert result == []


# ── get_player_presence_state ─────────────────────────────────────────────────


class TestGetPlayerPresenceState:
    def test_no_packets_state_is_neither(self):
        cap = _cap()
        cap.last_update = 0.0  # stale
        cap.packet_counts = {k: 0 for k in cap.packet_counts}
        cap.unknown_packets = 0
        result = RaceStateView(cap).get_player_presence_state()
        assert result["state"] == "neither"

    def test_in_game_with_live_signals(self):
        cap = _cap(
            session={
                "sessionTypeName": "Race",
                "gameModeName": "Grand Prix",
                "trackName": "Barcelona",
            },
            laps=[{"currentLapNum": 5, "carPosition": 3}],
        )
        cap.last_update = time.time()
        cap.packet_counts[1] = 100
        result = RaceStateView(cap).get_player_presence_state(confirm_samples=1)
        assert result["state"] == "in_game"

    def test_confirm_samples_1_updates_immediately(self):
        cap = _cap(
            session={
                "sessionTypeName": "Race",
                "gameModeName": "Grand Prix",
                "trackName": "Barcelona",
            },
            laps=[{"currentLapNum": 5, "carPosition": 3}],
        )
        cap.last_update = time.time()
        cap.packet_counts[1] = 50
        result = RaceStateView(cap).get_player_presence_state(confirm_samples=1)
        assert result["confirmSamples"] == 1
