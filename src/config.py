from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config.json"

DEFAULTS: dict[str, Any] = {
    "udpPort": 20777,
    "serverPort": 8080,
    "sessionTypes": ["Race", "Race 2", "Race 3"],
    "ttsVoice": "Alex",
    "overlayPosition": "right",
    "overlayDismissSpeed": "normal",
}


def load() -> dict[str, Any]:
    try:
        data = json.loads(_CONFIG_PATH.read_text("utf-8"))
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)
