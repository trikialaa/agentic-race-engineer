from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class SessionStore:
    snapshot: Dict[str, Any] = field(default_factory=dict)
    changes: deque = field(default_factory=deque)
    forecast_history: deque = field(default_factory=deque)
    forecast_latest: Optional[Any] = None
    safety_periods: List[Dict[str, Any]] = field(default_factory=list)
    marshal_latest: List[Any] = field(default_factory=list)
    marshal_changes: deque = field(default_factory=deque)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **dict(self.snapshot),
            "changes": list(self.changes),
            "forecastLatest": self.forecast_latest,
            "forecastHistory": list(self.forecast_history),
            "safetyPeriods": list(self.safety_periods),
            "marshalZones": {
                "latest": [dict(zone) if isinstance(zone, dict) else zone for zone in self.marshal_latest],
                "changes": list(self.marshal_changes),
            },
        }


@dataclass
class CarHistoryBuffers:
    car_telemetry: List[deque]
    car_status: List[deque]
    car_damage: List[deque]
    car_setups: List[deque]

    @classmethod
    def build(cls, buffer_sizes: Dict[str, int], max_cars: int) -> "CarHistoryBuffers":
        return cls(
            car_telemetry=[deque(maxlen=buffer_sizes["car_telemetry"]) for _ in range(max_cars)],
            car_status=[deque(maxlen=buffer_sizes["car_status"]) for _ in range(max_cars)],
            car_damage=[deque(maxlen=buffer_sizes["car_damage"]) for _ in range(max_cars)],
            car_setups=[deque(maxlen=buffer_sizes["car_setups"]) for _ in range(max_cars)],
        )
