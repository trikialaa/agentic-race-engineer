"""Unit tests for F1TelemetryCapture event classification and update logic.

No UDP socket, no game — tests operate directly on the capture object.
"""

from __future__ import annotations

import time

from src.live_data_engine.capture import F1TelemetryCapture


def _cap(player_idx: int = 0, laps: list | None = None) -> F1TelemetryCapture:
    cap = F1TelemetryCapture()
    cap.player_car_index = player_idx
    if laps is not None:
        cap.data["lap_data"]["laps"] = laps
    return cap


# ── _event_vehicle_indices ────────────────────────────────────────────────────


class TestEventVehicleIndices:
    def test_non_dict_returns_empty(self):
        cap = _cap()
        assert cap._event_vehicle_indices(None) == []
        assert cap._event_vehicle_indices("string") == []
        assert cap._event_vehicle_indices(42) == []

    def test_empty_dict_returns_empty(self):
        assert _cap()._event_vehicle_indices({}) == []

    def test_vehicle_idx_extracted(self):
        result = _cap()._event_vehicle_indices({"vehicleIdx": 3})
        assert 3 in result

    def test_other_vehicle_idx_extracted(self):
        result = _cap()._event_vehicle_indices({"otherVehicleIdx": 5})
        assert 5 in result

    def test_overtake_indices_extracted(self):
        result = _cap()._event_vehicle_indices(
            {
                "overtakingVehicleIdx": 2,
                "beingOvertakenVehicleIdx": 7,
            }
        )
        assert 2 in result
        assert 7 in result

    def test_negative_idx_excluded(self):
        result = _cap()._event_vehicle_indices({"vehicleIdx": -1})
        assert -1 not in result


# ── _is_nearby_vehicle_locked ─────────────────────────────────────────────────


class TestIsNearbyVehicleLocked:
    def test_empty_laps_returns_false(self):
        assert not _cap()._is_nearby_vehicle_locked(0)

    def test_out_of_range_vehicle_returns_false(self):
        cap = _cap(laps=[{"carPosition": 1}])
        assert not cap._is_nearby_vehicle_locked(5)

    def test_adjacent_position_returns_true(self):
        cap = _cap(
            player_idx=0,
            laps=[{"carPosition": 3}, {"carPosition": 4}],
        )
        assert cap._is_nearby_vehicle_locked(1)

    def test_three_positions_away_returns_true(self):
        cap = _cap(
            player_idx=0,
            laps=[{"carPosition": 1}, {"carPosition": 4}],
        )
        assert cap._is_nearby_vehicle_locked(1)

    def test_four_positions_away_returns_false(self):
        cap = _cap(
            player_idx=0,
            laps=[{"carPosition": 1}, {"carPosition": 5}],
        )
        assert not cap._is_nearby_vehicle_locked(1)

    def test_zero_position_returns_false(self):
        cap = _cap(
            player_idx=0,
            laps=[{"carPosition": 0}, {"carPosition": 0}],
        )
        assert not cap._is_nearby_vehicle_locked(1)


# ── _classify_event_locked ────────────────────────────────────────────────────


class TestClassifyEventLocked:
    def _classify(self, code, details, player_idx=0, laps=None):
        cap = _cap(player_idx=player_idx, laps=laps)
        with cap.lock:
            return cap._classify_event_locked(code, details)

    # Ignored codes
    def test_sptp_ignored(self):
        assert self._classify("SPTP", {}) == "ignored"

    def test_flbk_ignored(self):
        assert self._classify("FLBK", {}) == "ignored"

    def test_butn_ignored(self):
        assert self._classify("BUTN", {}) == "ignored"

    # Critical by code
    def test_rdfl_critical(self):
        assert self._classify("RDFL", {}) == "critical"

    def test_scar_critical(self):
        assert self._classify("SCAR", {}) == "critical"

    def test_chqf_critical(self):
        assert self._classify("CHQF", {}) == "critical"

    # COLL
    def test_coll_player_involved_critical(self):
        assert self._classify("COLL", {"vehicleIdx": 0}) == "critical"

    def test_coll_nearby_relevant(self):
        laps = [{"carPosition": 1}, {"carPosition": 2}]
        assert self._classify("COLL", {"vehicleIdx": 1}, player_idx=0, laps=laps) == "relevant"

    def test_coll_far_informational(self):
        laps = [{"carPosition": 1}, {"carPosition": 15}]
        assert self._classify("COLL", {"vehicleIdx": 1}, player_idx=0, laps=laps) == "informational"

    # RTMT
    def test_rtmt_player_critical(self):
        assert self._classify("RTMT", {"vehicleIdx": 0}) == "critical"

    def test_rtmt_nearby_relevant(self):
        laps = [{"carPosition": 1}, {"carPosition": 2}]
        assert self._classify("RTMT", {"vehicleIdx": 1}, player_idx=0, laps=laps) == "relevant"

    def test_rtmt_far_informational(self):
        assert self._classify("RTMT", {"vehicleIdx": 5}) == "informational"

    # PENA
    def test_pena_player_drive_through_critical(self):
        assert (
            self._classify("PENA", {"vehicleIdx": 0, "penaltyTypeName": "Drive Through"})
            == "critical"
        )

    def test_pena_player_stop_go_critical(self):
        assert self._classify("PENA", {"vehicleIdx": 0, "penaltyTypeName": "Stop Go"}) == "critical"

    def test_pena_player_disqualified_critical(self):
        assert (
            self._classify("PENA", {"vehicleIdx": 0, "penaltyTypeName": "Disqualified"})
            == "critical"
        )

    def test_pena_player_time_penalty_critical(self):
        assert (
            self._classify("PENA", {"vehicleIdx": 0, "penaltyTypeName": "Other", "time": 5})
            == "critical"
        )

    def test_pena_player_minor_relevant(self):
        assert (
            self._classify("PENA", {"vehicleIdx": 0, "penaltyTypeName": "Corner Cutting"})
            == "relevant"
        )

    def test_pena_rival_nearby_relevant(self):
        laps = [{"carPosition": 1}, {"carPosition": 2}]
        assert self._classify("PENA", {"vehicleIdx": 1}, player_idx=0, laps=laps) == "relevant"

    def test_pena_rival_far_informational(self):
        assert self._classify("PENA", {"vehicleIdx": 5}) == "informational"

    # DRSE always informational
    def test_drse_informational(self):
        assert self._classify("DRSE", {}) == "informational"
        assert self._classify("DRSE", {"vehicleIdx": 0}) == "informational"

    # DRSD
    def test_drsd_player_relevant(self):
        assert self._classify("DRSD", {"vehicleIdx": 0}) == "relevant"

    def test_drsd_far_still_relevant(self):
        # DRSD is always relevant (in {"DRSD", "TMPT", "FTLP", "RCWN"} with code in set)
        assert self._classify("DRSD", {}) == "relevant"

    # FTLP
    def test_ftlp_player_relevant(self):
        assert self._classify("FTLP", {"vehicleIdx": 0}) == "relevant"

    def test_ftlp_far_informational(self):
        assert self._classify("FTLP", {"vehicleIdx": 5}) == "informational"

    # RCWN always relevant
    def test_rcwn_relevant(self):
        assert self._classify("RCWN", {}) == "relevant"

    # OVTK
    def test_ovtk_player_overtaking_relevant(self):
        assert self._classify("OVTK", {"overtakingVehicleIdx": 0}) == "relevant"

    def test_ovtk_player_being_overtaken_relevant(self):
        assert self._classify("OVTK", {"beingOvertakenVehicleIdx": 0}) == "relevant"

    def test_ovtk_other_cars_informational(self):
        assert (
            self._classify("OVTK", {"overtakingVehicleIdx": 3, "beingOvertakenVehicleIdx": 5})
            == "informational"
        )

    # LLAP always relevant
    def test_llap_relevant(self):
        assert self._classify("LLAP", {}) == "relevant"

    # YELW
    def test_yelw_player_immediate_critical(self):
        assert (
            self._classify("YELW", {"localPlayerYellow": True, "immediateRisk": True}) == "critical"
        )

    def test_yelw_player_no_immediate_relevant(self):
        assert (
            self._classify("YELW", {"localPlayerYellow": True, "immediateRisk": False})
            == "relevant"
        )

    def test_yelw_not_player_informational(self):
        assert self._classify("YELW", {"localPlayerYellow": False}) == "informational"

    # Informational session codes
    def test_ssta_informational(self):
        assert self._classify("SSTA", {}) == "informational"

    def test_send_informational(self):
        assert self._classify("SEND", {}) == "informational"

    def test_dtsv_informational(self):
        assert self._classify("DTSV", {}) == "informational"

    # Unknown fallback
    def test_unknown_code_informational(self):
        assert self._classify("UNKN", {}) == "informational"
        assert self._classify("ABCD", {"vehicleIdx": 0}) == "informational"


# ── _emit_classified_event_locked ────────────────────────────────────────────


class TestEmitClassifiedEventLocked:
    def test_ignored_event_not_stored(self):
        cap = _cap()
        now = time.time()
        with cap.lock:
            cap._emit_classified_event_locked("SPTP", "Speed Trap", {}, now)
        assert len(cap.classified_event_stream) == 0

    def test_critical_event_stored(self):
        cap = _cap()
        now = time.time()
        with cap.lock:
            cap._emit_classified_event_locked("RDFL", "Red Flag", {}, now)
        assert len(cap.classified_event_stream) == 1
        assert cap.classified_event_stream[0]["code"] == "RDFL"

    def test_deduplication_suppresses_repeat(self):
        cap = _cap()
        now = time.time()
        with cap.lock:
            cap._emit_classified_event_locked("RDFL", "Red Flag", {}, now)
            cap._emit_classified_event_locked("RDFL", "Red Flag", {}, now + 0.1)
        # Second emit within TTL should be suppressed
        assert len(cap.classified_event_stream) == 1

    def test_event_after_ttl_fires_again(self):
        cap = _cap()
        cap._event_dedupe_ttl_s = 0.0  # disable TTL
        now = time.time()
        with cap.lock:
            cap._emit_classified_event_locked("RDFL", "Red Flag", {}, now)
            cap._emit_classified_event_locked("RDFL", "Red Flag", {}, now + 1.0)
        assert len(cap.classified_event_stream) == 2

    def test_event_stored_in_correct_severity_bucket(self):
        cap = _cap()
        now = time.time()
        with cap.lock:
            cap._emit_classified_event_locked("RDFL", "Red Flag", {}, now)
        assert len(cap.classified_events["critical"]) == 1
        assert len(cap.classified_events["relevant"]) == 0
        assert len(cap.classified_events["informational"]) == 0


# ── _update_data for event packets ───────────────────────────────────────────


class TestUpdateDataEvent:
    def test_null_event_code_not_stored(self):
        cap = _cap()
        cap._update_data("event", {"eventCode": "NULL", "details": {}})
        assert len(cap.data["event"]["eventHistory"]) == 0

    def test_empty_event_code_not_stored(self):
        cap = _cap()
        cap._update_data("event", {"eventCode": "", "details": {}})
        assert len(cap.data["event"]["eventHistory"]) == 0

    def test_valid_event_stored_in_history(self):
        cap = _cap()
        cap._update_data("event", {"eventCode": "RDFL", "details": {}})
        assert len(cap.data["event"]["eventHistory"]) == 1
        assert cap.data["event"]["eventHistory"][0]["code"] == "RDFL"

    def test_bytes_event_code_decoded(self):
        cap = _cap()
        cap._update_data("event", {"eventCode": b"RDFL", "details": {}})
        assert cap.data["event"]["eventHistory"][0]["code"] == "RDFL"

    def test_sptp_not_in_history(self):
        # SPTP is filtered out (ignored) and early-returned before history append
        cap = _cap()
        cap._update_data("event", {"eventCode": "SPTP", "details": {}})
        assert len(cap.data["event"]["eventHistory"]) == 0

    def test_event_history_capped_at_buffer_size(self):
        cap = _cap()
        cap.events_buffer_size = 3
        for i in range(5):
            cap._event_last_emitted.clear()  # bypass dedup
            cap._update_data("event", {"eventCode": "RDFL", "details": {"vehicleIdx": i}})
        assert len(cap.data["event"]["eventHistory"]) <= 3

    def test_motion_packet_preserves_history_by_lap(self):
        cap = _cap(laps=[{"currentLapNum": 5}])
        # Pre-existing lap bucket in the correct format; the update should preserve it
        cap.data["motion"]["historyByLap"] = [{"lapNum": 5, "samples": []}]
        cap._update_data("motion", {"cars": [], "playerExtra": {}})
        # historyByLap should still exist and contain the same lap bucket
        history = cap.data["motion"]["historyByLap"]
        assert isinstance(history, list)
        assert len(history) >= 1
        assert history[0]["lapNum"] == 5

    def test_tyre_sets_stored(self):
        cap = _cap()
        cap._update_data("tyre_sets", {"compound": "Soft"})
        assert cap.data["tyre_sets"]["latest"] == {"compound": "Soft"}
