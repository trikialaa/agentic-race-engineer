"""Unit tests for mcp/functions/race_report.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.mcp.functions.race_report import _fmt_ms, get_race_report

# ── _fmt_ms ───────────────────────────────────────────────────────────────────


class TestFmtMs:
    def test_zero_returns_none(self):
        assert _fmt_ms(0) is None

    def test_negative_returns_none(self):
        assert _fmt_ms(-1000) is None

    def test_none_returns_none(self):
        assert _fmt_ms(None) is None  # type: ignore[arg-type]

    def test_string_returns_none(self):
        assert _fmt_ms("1000") is None  # type: ignore[arg-type]

    def test_one_second(self):
        assert _fmt_ms(1000) == "0:01.000"

    def test_one_minute(self):
        assert _fmt_ms(60000) == "1:00.000"

    def test_lap_time_83962ms(self):
        result = _fmt_ms(83962)
        assert result is not None
        assert result.startswith("1:")
        assert "23.962" in result

    def test_sub_second(self):
        result = _fmt_ms(500)
        assert result == "0:00.500"


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_capture(final=None, events=(), participants=()):
    cap = MagicMock()
    cap.player_car_index = 0
    cap.query.get_final_classification.return_value = final
    cap.classified_event_stream = list(events)
    cap.data = {"participants": {"participants": list(participants)}}
    return cap


def _classification_entry(**kwargs):
    defaults = {
        "position": 1,
        "gridPosition": 3,
        "numLaps": 66,
        "numPitStops": 1,
        "bestLapTimeInMS": 83962,
        "totalRaceTime": 5400.0,
        "penaltiesTime": None,
        "numPenalties": 0,
        "resultReasonName": "Finished",
        "numTyreStints": 1,
        "tyreStintsVisual": [16],  # Soft
        "tyreStintsEndLaps": [66],
    }
    defaults.update(kwargs)
    return defaults


# ── get_race_report ───────────────────────────────────────────────────────────


class TestGetRaceReportUnavailable:
    def test_no_final_classification(self):
        cap = _make_capture(final=None)
        result = get_race_report(cap)
        assert result["available"] is False
        # _strip_nulls converts None to 'unknown' rather than removing the key
        assert result.get("results") == "unknown"

    def test_empty_classification_data(self):
        cap = _make_capture(final={"numCars": 0, "classificationData": []})
        result = get_race_report(cap)
        assert result["available"] is False

    def test_all_positions_zero_skipped(self):
        cap = _make_capture(final={"numCars": 1, "classificationData": [{"position": 0}]})
        result = get_race_report(cap)
        assert result["available"] is False


class TestGetRaceReportResults:
    def test_basic_result_returned(self):
        cap = _make_capture(
            final={"numCars": 1, "classificationData": [_classification_entry()]},
            participants=[{"name": "Lewis Hamilton", "teamName": "Mercedes"}],
        )
        result = get_race_report(cap)
        assert result["available"] is True
        assert len(result["results"]) == 1
        entry = result["results"][0]
        assert entry["position"] == 1
        assert entry["name"] == "Lewis Hamilton"
        assert entry["team"] == "Mercedes"

    def test_position_change_calculated(self):
        cap = _make_capture(
            final={
                "numCars": 1,
                "classificationData": [_classification_entry(position=1, gridPosition=3)],
            }
        )
        result = get_race_report(cap)
        assert result["results"][0]["positionChange"] == 2  # 3 - 1

    def test_position_change_negative(self):
        cap = _make_capture(
            final={
                "numCars": 1,
                "classificationData": [_classification_entry(position=5, gridPosition=2)],
            }
        )
        result = get_race_report(cap)
        assert result["results"][0]["positionChange"] == -3

    def test_is_player_flag(self):
        cap = _make_capture(final={"numCars": 1, "classificationData": [_classification_entry()]})
        cap.player_car_index = 0
        result = get_race_report(cap)
        assert result["results"][0]["isPlayer"] is True

    def test_best_lap_time_formatted(self):
        cap = _make_capture(
            final={
                "numCars": 1,
                "classificationData": [_classification_entry(bestLapTimeInMS=83962)],
            }
        )
        result = get_race_report(cap)
        assert "23.962" in result["results"][0]["bestLapTime"]

    def test_tyre_compound_soft(self):
        cap = _make_capture(
            final={
                "numCars": 1,
                "classificationData": [
                    _classification_entry(
                        numTyreStints=1, tyreStintsVisual=[16], tyreStintsEndLaps=[30]
                    )
                ],
            }
        )
        result = get_race_report(cap)
        assert result["results"][0]["tyreStints"][0]["compound"] == "Soft"
        assert result["results"][0]["tyreStints"][0]["endLap"] == 30

    def test_tyre_end_lap_255_becomes_none(self):
        cap = _make_capture(
            final={
                "numCars": 1,
                "classificationData": [
                    _classification_entry(
                        numTyreStints=1, tyreStintsVisual=[17], tyreStintsEndLaps=[255]
                    )
                ],
            }
        )
        result = get_race_report(cap)
        # endLap=255 → None → _strip_nulls converts to 'unknown'
        assert result["results"][0]["tyreStints"][0].get("endLap") == "unknown"

    def test_tyre_compounds_map(self):
        compounds = {16: "Soft", 17: "Medium", 18: "Hard", 7: "Inter", 8: "Wet"}
        for code, name in compounds.items():
            cap = _make_capture(
                final={
                    "numCars": 1,
                    "classificationData": [
                        _classification_entry(
                            numTyreStints=1, tyreStintsVisual=[code], tyreStintsEndLaps=[50]
                        )
                    ],
                }
            )
            result = get_race_report(cap)
            assert result["results"][0]["tyreStints"][0]["compound"] == name

    def test_unknown_compound_uses_hash_prefix(self):
        cap = _make_capture(
            final={
                "numCars": 1,
                "classificationData": [
                    _classification_entry(
                        numTyreStints=1, tyreStintsVisual=[99], tyreStintsEndLaps=[50]
                    )
                ],
            }
        )
        result = get_race_report(cap)
        assert result["results"][0]["tyreStints"][0]["compound"].startswith("#")

    def test_results_sorted_by_position(self):
        cap = _make_capture(
            final={
                "numCars": 2,
                "classificationData": [
                    _classification_entry(
                        position=2,
                        gridPosition=2,
                        numTyreStints=0,
                        tyreStintsVisual=[],
                        tyreStintsEndLaps=[],
                    ),
                    _classification_entry(
                        position=1,
                        gridPosition=1,
                        numTyreStints=0,
                        tyreStintsVisual=[],
                        tyreStintsEndLaps=[],
                    ),
                ],
            }
        )
        result = get_race_report(cap)
        positions = [e["position"] for e in result["results"]]
        assert positions == sorted(positions)

    def test_fallback_car_name_when_no_participant(self):
        cap = _make_capture(
            final={"numCars": 1, "classificationData": [_classification_entry()]},
            participants=[],  # no participant data
        )
        result = get_race_report(cap)
        assert "Car 0" in result["results"][0]["name"]

    def test_non_dict_classification_entry_skipped(self):
        cap = _make_capture(
            final={"numCars": 2, "classificationData": ["invalid", _classification_entry()]}
        )
        result = get_race_report(cap)
        assert len(result["results"]) == 1


class TestGetRaceReportNotableEvents:
    def test_ftlp_included(self):
        events = [
            {
                "code": "FTLP",
                "eventName": "Fastest Lap",
                "time": "12:00",
                "involvesPlayer": True,
                "details": {},
            }
        ]
        cap = _make_capture(events=events)
        result = get_race_report(cap)
        codes = [e["code"] for e in (result.get("notableEvents") or [])]
        assert "FTLP" in codes

    def test_pena_included(self):
        events = [
            {
                "code": "PENA",
                "eventName": "Penalty",
                "time": "12:00",
                "involvesPlayer": False,
                "details": {},
            }
        ]
        cap = _make_capture(events=events)
        result = get_race_report(cap)
        codes = [e["code"] for e in (result.get("notableEvents") or [])]
        assert "PENA" in codes

    def test_coll_excluded(self):
        events = [
            {
                "code": "COLL",
                "eventName": "Collision",
                "time": "12:00",
                "involvesPlayer": False,
                "details": {},
            }
        ]
        cap = _make_capture(events=events)
        result = get_race_report(cap)
        notable = result.get("notableEvents")
        # COLL is not in report_codes so notableEvents is None → 'unknown'
        assert notable == "unknown"

    def test_no_notable_events_is_unknown(self):
        # When there are no notable events, _strip_nulls converts None → 'unknown'
        cap = _make_capture()
        result = get_race_report(cap)
        assert result.get("notableEvents") == "unknown"
