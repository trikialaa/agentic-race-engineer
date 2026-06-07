from __future__ import annotations

import time
from typing import Any


def _strip_nulls(obj: Any) -> Any:
    """Recursively replace None values with 'unknown' so the LLM knows the field exists but data is unavailable."""
    if isinstance(obj, dict):
        return {k: _strip_nulls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_nulls(v) for v in obj]
    if obj is None:
        return "unknown"
    return obj


def _round(value: Any, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _clock_now() -> str:
    now = time.time()
    local = time.localtime(now)
    ms = int((now - int(now)) * 1000)
    return time.strftime("%H:%M:%S", local) + f".{ms:03d}"


def _parse_lap_time_seconds(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text in ("00:00.000", "0:00.000"):
        return None
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    except Exception:
        return None


def _normalize_tyre_compound(compound: Any) -> str | None:
    if not isinstance(compound, str) or not compound.strip():
        return None
    normalized = compound.strip().lower()
    mapping = {
        "soft": "soft",
        "medium": "medium",
        "hard": "hard",
        "inter": "inter",
        "intermediate": "inter",
        "wet": "wet",
    }
    if normalized in mapping:
        return mapping[normalized]
    c_compound_map = {"c1": "hard", "c2": "hard", "c3": "medium", "c4": "soft", "c5": "soft"}
    if normalized in c_compound_map:
        return c_compound_map[normalized]
    if "inter" in normalized:
        return "inter"
    if "wet" in normalized:
        return "wet"
    return None


def _pit_status_value(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text == "none":
            return "none"
        return text
    return str(value)


def _abs_round(value: Any, digits: int = 2) -> float | None:
    rounded = _round(value, digits)
    if rounded is None:
        return None
    return abs(rounded)


def _normalize_safety_car(value: Any) -> str:
    if not isinstance(value, str):
        return "none"
    text = value.strip().lower()
    if text in ("vsc", "virtual safety car"):
        return "vsc"
    if "safety car" in text and "no " not in text:
        return "sc"
    return "none"


def _normalize_flag(value: Any) -> str:
    if not isinstance(value, str):
        return "none"
    text = value.strip().lower()
    if not text or text == "none":
        return "none"
    if text == "invalid/unknown":
        return "none"
    return text
