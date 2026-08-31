"""Unit tests for src/mcp/functions/_shared.py helpers."""

import pytest

from src.mcp.functions._shared import (
    _abs_round,
    _clock_now,
    _normalize_flag,
    _normalize_safety_car,
    _normalize_tyre_compound,
    _parse_lap_time_seconds,
    _pit_status_value,
    _round,
    _strip_nulls,
)


class TestStripNulls:
    def test_none_becomes_unknown(self):
        assert _strip_nulls(None) == "unknown"

    def test_dict_values_recursed(self):
        assert _strip_nulls({"a": None, "b": 1}) == {"a": "unknown", "b": 1}

    def test_list_items_recursed(self):
        assert _strip_nulls([None, "x", None]) == ["unknown", "x", "unknown"]

    def test_nested(self):
        assert _strip_nulls({"a": {"b": None}}) == {"a": {"b": "unknown"}}

    def test_non_none_passthrough(self):
        assert _strip_nulls(42) == 42
        assert _strip_nulls("hello") == "hello"


class TestRound:
    def test_rounds_to_1dp_by_default(self):
        assert _round(1.234) == 1.2

    def test_rounds_to_n_digits(self):
        assert _round(1.2345, 3) == 1.234

    def test_none_returns_none(self):
        assert _round(None) is None

    def test_string_float_coerced(self):
        assert _round("3.567") == 3.6

    def test_invalid_returns_none(self):
        assert _round("abc") is None


class TestClockNow:
    def test_format(self):
        result = _clock_now()
        assert len(result) == 12  # HH:MM:SS.mmm
        assert result[2] == ":" and result[5] == ":" and result[8] == "."
        ms = result[9:]
        assert ms.isdigit() and len(ms) == 3


class TestParseLapTimeSeconds:
    def test_valid_time(self):
        result = _parse_lap_time_seconds("1:21.197")
        assert result == pytest.approx(81.197, abs=0.001)

    def test_zero_time_returns_none(self):
        assert _parse_lap_time_seconds("00:00.000") is None
        assert _parse_lap_time_seconds("0:00.000") is None

    def test_none_input(self):
        assert _parse_lap_time_seconds(None) is None

    def test_non_string(self):
        assert _parse_lap_time_seconds(81.197) is None

    def test_malformed(self):
        assert _parse_lap_time_seconds("badformat") is None


class TestNormalizeTyreCompound:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("soft", "soft"),
            ("SOFT", "soft"),
            ("Soft", "soft"),
            ("medium", "medium"),
            ("hard", "hard"),
            ("inter", "inter"),
            ("intermediate", "inter"),
            ("wet", "wet"),
            ("C4", "soft"),
            ("C3", "medium"),
            ("C2", "hard"),
            ("unknown_compound", None),
            ("", None),
            (None, None),
            (42, None),
        ],
    )
    def test_compound_mapping(self, inp, expected):
        assert _normalize_tyre_compound(inp) == expected


class TestPitStatusValue:
    def test_none_returns_none_string(self):
        assert _pit_status_value(None) == "none"

    def test_empty_string_returns_none(self):
        assert _pit_status_value("") == "none"

    def test_none_string_passthrough(self):
        assert _pit_status_value("none") == "none"

    def test_pit_status_lowercased(self):
        assert _pit_status_value("In Pit") == "in pit"


class TestAbsRound:
    def test_positive(self):
        assert _abs_round(3.567, 2) == 3.57

    def test_negative_returns_positive(self):
        assert _abs_round(-3.567, 2) == 3.57

    def test_none_returns_none(self):
        assert _abs_round(None) is None


class TestNormalizeSafetyCar:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("Safety Car", "full_safety_car"),
            ("Full Safety Car", "full_safety_car"),
            ("Virtual Safety Car", "virtual_safety_car"),
            ("VSC", "virtual_safety_car"),
            ("No Safety Car", "none"),
            ("none", "none"),
            ("", "none"),
            (None, "none"),
            (42, "none"),
        ],
    )
    def test_safety_car_values(self, inp, expected):
        assert _normalize_safety_car(inp) == expected


class TestNormalizeFlag:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("none", "none"),
            ("", "none"),
            ("invalid/unknown", "none"),
            ("yellow", "yellow"),
            ("GREEN", "green"),
            (None, "none"),
            (0, "none"),
        ],
    )
    def test_flag_values(self, inp, expected):
        assert _normalize_flag(inp) == expected
