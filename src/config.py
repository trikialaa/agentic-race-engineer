from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config.json"

DEFAULTS: dict[str, Any] = {
    "udpPort": 20777,
    "serverPort": 8080,
    "sessionTypes": ["Race", "Race 2", "Feature Race"],
    "overlayPosition": "right",
    "overlayDismissSpeed": "normal",
    "engineerCallouts": "critical",
}


def load() -> dict[str, Any]:
    try:
        data = json.loads(_CONFIG_PATH.read_text("utf-8"))
        merged = {**DEFAULTS, **data}
        # Back-compat: migrate old key on first load; it rewrites on next Save.
        if "proactiveEvents" in merged and "engineerCallouts" not in data:
            merged["engineerCallouts"] = merged.pop("proactiveEvents")
        return merged
    except Exception:
        return dict(DEFAULTS)


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)
