import logging
import os
import socket
import threading
import time
from collections import deque
from typing import Dict, Any, Optional, List, Tuple

from src.live_data_engine.cache import CarHistoryBuffers, SessionStore
from src.live_data_engine.query import RaceStateView
from src.udp_parser import (
    PacketHeader,
    PACKET_ID,
    decode_motion,
    decode_session,
    decode_lap_data,
    decode_event,
    decode_participants,
    decode_car_setups,
    decode_car_telemetry,
    decode_car_status,
    decode_final_classification,
    decode_lobby_info,
    decode_car_damage,
    decode_session_history,
    decode_motion_ex,
    decode_tyre_sets,
    decode_time_trial,
    decode_lap_positions,
)
from src.udp_parser.constants import (
    EVENT_CODES,
    SESSION_WATCH_KEYS,
    SESSION_FORECAST_KEYS,
    SESSION_MARSHAL_KEYS,
)

logger = logging.getLogger(__name__)

PACKET_TYPES = {
    0: ("motion", decode_motion),
    1: ("session", decode_session),
    2: ("lap_data", decode_lap_data),
    3: ("event", decode_event),
    4: ("participants", decode_participants),
    5: ("car_setups", decode_car_setups),
    6: ("car_telemetry", decode_car_telemetry),
    7: ("car_status", decode_car_status),
    8: ("final_classification", decode_final_classification),
    9: ("lobby_info", decode_lobby_info),
    10: ("car_damage", decode_car_damage),
    11: ("session_history", decode_session_history),
    12: ("tyre_sets", decode_tyre_sets),
    13: ("motion_ex", decode_motion_ex),
    14: ("time_trial", decode_time_trial),
    15: ("lap_positions", decode_lap_positions),
}


class F1TelemetryCapture:
    """Captures and stores F1 telemetry data from UDP packets"""
    
    def __init__(self, bind_ip: str = "0.0.0.0", port: int = 20777):
        self.bind_ip = bind_ip
        self.port = port
        self.running = False
        self.thread = None
        self.sock = None
        self.lock = threading.Lock()
        self.packet_counts = {pid: 0 for pid in PACKET_TYPES.keys()}
        self.unknown_packets = 0
        self.error_count = 0
        self.last_header: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.format_mismatch: Optional[int] = None

        self.player_car_index = 0
        self.last_update = time.time()
        # Configurable buffers
        self.events_buffer_size = int(os.getenv("F1_EVENTS_BUFFER", "100"))
        self.buffer_sizes = {
            "car_telemetry": int(os.getenv("F1_BUFFER_CAR_TELEMETRY", "120")),
            "car_status": int(os.getenv("F1_BUFFER_CAR_STATUS", "100")),
            "car_damage": int(os.getenv("F1_BUFFER_CAR_DAMAGE", "100")),
            "lap_events": int(os.getenv("F1_BUFFER_LAP_EVENTS", "200")),
            "car_setups": int(os.getenv("F1_BUFFER_CAR_SETUPS", "20")),
            "session": int(os.getenv("F1_BUFFER_SESSION", "200")),
            "forecast": int(os.getenv("F1_BUFFER_FORECAST", "50")),
            "marshal": int(os.getenv("F1_BUFFER_MARSHAL", "200")),
            "motion_laps": int(os.getenv("F1_BUFFER_MOTION_LAPS", "5")),
            "motion_samples": int(os.getenv("F1_BUFFER_MOTION_SAMPLES", "300")),
            "lap_history": int(os.getenv("F1_BUFFER_LAP_HISTORY", "50")),
            "position_changes": int(os.getenv("F1_BUFFER_POSITION_CHANGES", "200")),
            "pit_events": int(os.getenv("F1_BUFFER_PIT_EVENTS", "100")),
        }

        self.max_cars = 22
        self.session_store = SessionStore()
        self.session_store.changes = deque(maxlen=self.buffer_sizes["session"])
        self.session_store.forecast_history = deque(maxlen=self.buffer_sizes["forecast"])
        self.session_store.marshal_changes = deque(maxlen=self.buffer_sizes["marshal"])
        self.car_history = CarHistoryBuffers.build(self.buffer_sizes, self.max_cars)

        # Telemetry data storage (latest snapshots)
        self.data = {
            "session": self.session_store.to_dict(),
            "lap_data": {"laps": []},
            "car_telemetry": {"carTelemetry": []},
            "car_status": {"carStatus": []},
            "car_damage": {"carDamage": []},
            "participants": {"participants": []},
            # motion will include an in-structure ring buffer by lap
            "motion": {"cars": [], "playerExtra": {}, "historyByLap": []},
            "event": {"eventHistory": []},
            "car_setups": {"carSetups": []},
            "lobby_info": {"lobbyPlayers": []},
            "tyre_sets": {"latest": None},
            "motion_ex": {"playerExtra": {}},
            "time_trial": {
                "playerSessionBestDataSet": None,
                "personalBestDataSet": None,
                "rivalDataSet": None,
            },
            "lap_positions": {"positions": [], "numLaps": 0, "lapStart": 0},
            "final_classification": None,
            "session_history": None
        }
        self.session_history_by_car: List[Optional[Dict[str, Any]]] = [None for _ in range(self.max_cars)]
        self.classified_events = {
            "critical": deque(maxlen=self.events_buffer_size),
            "relevant": deque(maxlen=self.events_buffer_size),
            "informational": deque(maxlen=self.events_buffer_size),
        }
        self.classified_event_stream = deque(maxlen=self.events_buffer_size * 2)
        self._event_dedupe_ttl_s = 2.0
        self._event_last_emitted: Dict[str, float] = {}
        self._last_player_yellow: Optional[bool] = None

        # Track last seen states per car
        self._last_lap_num = [0 for _ in range(self.max_cars)]
        self._last_position = [0 for _ in range(self.max_cars)]
        self._last_pit_status = [None for _ in range(self.max_cars)]
        self._presence_state = "neither"
        self._presence_reason = "stale_or_no_packets"
        self._presence_candidate_state: Optional[str] = None
        self._presence_candidate_reason: Optional[str] = None
        self._presence_candidate_count = 0
        self._presence_last_transition: Optional[float] = None

        self.query = RaceStateView(self)

    def _event_vehicle_indices(self, details: Any) -> List[int]:
        if not isinstance(details, dict):
            return []
        idxs = []
        for key in (
            "vehicleIdx",
            "otherVehicleIdx",
            "overtakingVehicleIdx",
            "beingOvertakenVehicleIdx",
            "vehicle1Idx",
            "vehicle2Idx",
        ):
            val = details.get(key)
            if isinstance(val, int) and val >= 0:
                idxs.append(val)
        return idxs

    def _is_nearby_vehicle_locked(self, vehicle_idx: int, window: int = 3) -> bool:
        laps = self.data.get("lap_data", {}).get("laps", []) or []
        if not (0 <= vehicle_idx < len(laps) and 0 <= self.player_car_index < len(laps)):
            return False
        try:
            player_pos = int((laps[self.player_car_index] or {}).get("carPosition") or 0)
            other_pos = int((laps[vehicle_idx] or {}).get("carPosition") or 0)
        except Exception:
            return False
        if player_pos <= 0 or other_pos <= 0:
            return False
        return abs(player_pos - other_pos) <= max(1, window)

    def _player_immediate_proximity_risk_locked(self) -> bool:
        laps = self.data.get("lap_data", {}).get("laps", []) or []
        telemetry = self.data.get("car_telemetry", {}).get("carTelemetry", []) or []
        if not (0 <= self.player_car_index < len(laps)):
            return False
        player_lap = laps[self.player_car_index] if isinstance(laps[self.player_car_index], dict) else {}
        player_pos = player_lap.get("carPosition")
        if not isinstance(player_pos, int) or player_pos <= 0:
            return False
        player_total = player_lap.get("totalDistance")
        if not isinstance(player_total, (int, float)):
            return False
        player_speed = 0.0
        if 0 <= self.player_car_index < len(telemetry):
            tel = telemetry[self.player_car_index] if isinstance(telemetry[self.player_car_index], dict) else {}
            sp = tel.get("speedKph")
            if isinstance(sp, (int, float)):
                player_speed = float(sp) / 3.6
        for idx, lap in enumerate(laps):
            if idx == self.player_car_index or not isinstance(lap, dict):
                continue
            other_pos = lap.get("carPosition")
            if not isinstance(other_pos, int) or abs(other_pos - player_pos) != 1:
                continue
            other_total = lap.get("totalDistance")
            if not isinstance(other_total, (int, float)):
                continue
            other_speed = 0.0
            if 0 <= idx < len(telemetry):
                tel = telemetry[idx] if isinstance(telemetry[idx], dict) else {}
                sp = tel.get("speedKph")
                if isinstance(sp, (int, float)):
                    other_speed = float(sp) / 3.6
            avg_speed = max((player_speed + other_speed) / 2.0, 0.1)
            gap_s = abs(float(other_total) - float(player_total)) / avg_speed
            if gap_s <= 1.2:
                return True
        return False

    def _classify_event_locked(self, code: str, details: Dict[str, Any], event_name: str = "") -> str:
        ignored = {"SPTP", "FLBK", "BUTN"}
        if code in ignored:
            return "ignored"

        player_idx = self.player_car_index
        vehicles = self._event_vehicle_indices(details)
        involves_player = player_idx in vehicles
        nearby = any(self._is_nearby_vehicle_locked(idx) for idx in vehicles if idx != player_idx)

        if code in {"RDFL", "SCAR", "CHQF"}:
            return "critical"
        if code == "COLL":
            return "critical" if involves_player else ("relevant" if nearby else "informational")
        if code == "RTMT":
            return "critical" if involves_player else ("relevant" if nearby else "informational")
        if code == "PENA":
            penalty_name = str(details.get("penaltyTypeName") or "").lower()
            penalty_time = details.get("time")
            if involves_player:
                if any(token in penalty_name for token in ("drive through", "stop go", "disqualified", "grid", "time penalty")):
                    return "critical"
                if isinstance(penalty_time, int) and penalty_time > 0:
                    return "critical"
                return "relevant"
            return "relevant" if nearby else "informational"
        if code in {"OVTK", "DRSE", "DRSD", "TMPT", "FTLP", "RCWN"}:
            return "relevant" if (involves_player or nearby or code in {"DRSE", "DRSD", "RCWN"}) else "informational"
        if code in {"SSTA", "SEND", "STLG", "LGOT", "DTSV", "SGSV"}:
            return "informational"
        if code == "YELW":
            if details.get("localPlayerYellow"):
                return "critical" if details.get("immediateRisk") else "relevant"
            return "informational"
        return "informational"

    def _emit_classified_event_locked(self, code: str, event_name: str, details: Dict[str, Any], now: float) -> None:
        severity = self._classify_event_locked(code, details, event_name=event_name)
        if severity == "ignored":
            return
        vehicles = self._event_vehicle_indices(details)
        involves_player = self.player_car_index in vehicles
        key = f"{severity}|{code}|{involves_player}|{details.get('vehicleIdx')}|{details.get('otherVehicleIdx')}|{details.get('time')}|{details.get('lapNum')}|{details.get('eventType')}"
        last = self._event_last_emitted.get(key)
        if isinstance(last, float) and now - last < self._event_dedupe_ttl_s:
            return
        self._event_last_emitted[key] = now
        if len(self._event_last_emitted) > 500:
            cutoff = now - 60.0
            self._event_last_emitted = {k: v for k, v in self._event_last_emitted.items() if v > cutoff}
        entry = {
            "code": code,
            "eventName": event_name,
            "details": details,
            "time": time.strftime("%H:%M:%S"),
            "ts": now,
            "severity": severity,
            "involvesPlayer": involves_player,
        }
        if severity in self.classified_events:
            self.classified_events[severity].appendleft(entry)
        self.classified_event_stream.appendleft(entry)
        
    def start_capture(self):
        """Start capturing telemetry data in a background thread"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info(f"Started F1 telemetry capture on {self.bind_ip}:{self.port}")
        
    def stop_capture(self):
        """Stop capturing telemetry data"""
        self.running = False
        if self.sock:
            self.sock.close()
        if self.thread:
            self.thread.join(timeout=1.0)
        logger.info("Stopped F1 telemetry capture")
        
    def _capture_loop(self):
        """Main capture loop running in background thread"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.bind_ip, self.port))
            self.sock.settimeout(0.1)
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(8192)
                    buf = memoryview(data)

                    # Parse header
                    hdr = PacketHeader.from_buf(buf)
                    pid = hdr.m_packetId
                    if hdr.m_packetFormat != 2025 and self.format_mismatch != hdr.m_packetFormat:
                        self.format_mismatch = hdr.m_packetFormat
                        logger.warning(f"Packet format {hdr.m_packetFormat} differs from expected 2025; decoders may be incompatible")
                    self.last_header = {
                        "format": hdr.m_packetFormat,
                        "packetVersion": getattr(hdr, "m_packetVersion", None),
                        "packetId": pid,
                        "sessionUID": getattr(hdr, "m_sessionUID", None),
                        "sessionTime": getattr(hdr, "m_sessionTime", None),
                        "frame": getattr(hdr, "m_frameIdentifier", None),
                        "overallFrame": getattr(hdr, "m_overallFrameIdentifier", None),
                        "gameYear": getattr(hdr, "m_gameYear", None),
                        "playerCarIndex": getattr(hdr, "m_playerCarIndex", None),
                    }

                    # Update player car index
                    if hasattr(hdr, 'm_playerCarIndex'):
                        with self.lock:
                            self.player_car_index = hdr.m_playerCarIndex

                    # Process packet if it's one we're interested in
                    if pid in PACKET_TYPES:
                        packet_name, decoder = PACKET_TYPES[pid]
                        payload = decoder(buf)
                        self._update_data(packet_name, payload)
                        self.packet_counts[pid] = self.packet_counts.get(pid, 0) + 1
                    else:
                        self.unknown_packets += 1
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    self.error_count += 1
                    self.last_error = str(e)
                    logger.error(f"Error processing packet: {e}")
                    
        except Exception as e:
            logger.error(f"Error in capture loop: {e}")
        finally:
            if self.sock:
                self.sock.close()
                
    def _update_data(self, packet_type: str, data: Dict[str, Any]):
        """Update stored telemetry data and histories (thread-safe)"""
        now = time.time()
        with self.lock:
            if packet_type == "event":
                # Handle events specially - keep history
                event_code = data.get("eventCode", "")
                if isinstance(event_code, (bytes, bytearray)):
                    try:
                        event_code = event_code.decode("ascii", "ignore").strip()
                    except Exception:
                        event_code = str(event_code)
                if event_code and event_code != "NULL":
                    details = data.get("details", {})
                    event_name = EVENT_CODES.get(event_code, event_code)
                    self._emit_classified_event_locked(event_code, event_name, details if isinstance(details, dict) else {}, now)
                    if event_code in {"SPTP", "FLBK", "BUTN"}:
                        self.last_update = now
                        return
                    event_entry = {
                        "code": event_code,
                        "eventName": event_name,
                        "details": details,
                        "time": time.strftime("%H:%M:%S")
                    }
                    self.data[packet_type]["eventHistory"].insert(0, event_entry)
                    # Keep only last N events
                    self.data[packet_type]["eventHistory"] = self.data[packet_type]["eventHistory"][: self.events_buffer_size]
                self.last_update = now
                return

            # For non-event packets, always store latest snapshot (with special handling)
            if packet_type == "motion":
                # Preserve existing historyByLap when replacing motion snapshot
                prev = self.data.get("motion") or {}
                history = prev.get("historyByLap") if isinstance(prev, dict) else None
                if not isinstance(history, list):
                    history = []
                new_motion = dict(data) if isinstance(data, dict) else {"raw": data}
                new_motion["historyByLap"] = history
                self.data[packet_type] = new_motion
            elif packet_type == "motion_ex":
                self.data["motion_ex"] = data
                motion = self.data.get("motion", {})
                if isinstance(motion, dict):
                    motion["playerExtra"] = data.get("playerExtra", {})
                self.last_update = now
                return
            elif packet_type == "session":
                session_store = self.session_store
                prev_snapshot = dict(session_store.snapshot)
                changes = session_store.changes
                forecast_history = session_store.forecast_history
                safety_periods = session_store.safety_periods
                marshal_changes = session_store.marshal_changes
                prev_marshal = list(session_store.marshal_latest)

                new_snapshot = {}
                if isinstance(data, dict):
                    new_snapshot.update(data)

                prev_sc = prev_snapshot.get("safetyCarStatusName")
                curr_sc = new_snapshot.get("safetyCarStatusName")
                if curr_sc != prev_sc:
                    if prev_sc and prev_sc.lower() in ("vsc", "virtual safety car", "sc", "safety car") and (
                        not curr_sc or curr_sc.lower() == "none"
                    ):
                        for sp in reversed(safety_periods):
                            if sp.get("endTime") is None:
                                sp["endTime"] = now
                                break
                    if curr_sc and curr_sc.lower() in ("vsc", "virtual safety car", "sc", "safety car"):
                        sp_type = "VSC" if "vsc" in curr_sc.lower() else "SC"
                        safety_periods.append({"type": sp_type, "startTime": now, "endTime": None})

                watch_keys = SESSION_WATCH_KEYS
                change_snap = {k: new_snapshot.get(k) for k in watch_keys if k in new_snapshot}
                if change_snap:
                    last = changes[0].get("data", {}) if changes else {}
                    if any(last.get(k) != change_snap.get(k) for k in change_snap.keys()):
                        changes.appendleft({"time": now, "data": change_snap})

                forecast_samples = None
                for key in SESSION_FORECAST_KEYS:
                    if key in new_snapshot:
                        forecast_samples = new_snapshot.get(key)
                        break
                if forecast_samples is not None:
                    session_store.forecast_latest = forecast_samples
                    should_append = not forecast_history or forecast_history[0].get("samples") != forecast_samples
                    if should_append:
                        forecast_history.appendleft({"time": now, "samples": forecast_samples})

                marshal_data = None
                for key in SESSION_MARSHAL_KEYS:
                    if key in new_snapshot:
                        marshal_data = new_snapshot.get(key)
                        break
                if marshal_data is not None:
                    new_marshal = []
                    if isinstance(marshal_data, list):
                        new_marshal = [dict(zone) if isinstance(zone, dict) else zone for zone in marshal_data]
                    else:
                        new_marshal = [marshal_data]
                    session_store.marshal_latest = new_marshal
                    if isinstance(new_marshal, list):
                        for idx, zone in enumerate(new_marshal):
                            curr_flag = None
                            if isinstance(zone, dict):
                                curr_flag = zone.get("flagColor") or zone.get("zoneFlagName") or zone.get("flag")
                            else:
                                curr_flag = zone
                            prev_flag = None
                            if idx < len(prev_marshal):
                                prev_zone = prev_marshal[idx]
                                if isinstance(prev_zone, dict):
                                    prev_flag = prev_zone.get("flagColor") or prev_zone.get("zoneFlagName") or prev_zone.get("flag")
                                else:
                                    prev_flag = prev_zone
                            if curr_flag != prev_flag:
                                marshal_changes.appendleft({"time": now, "zoneIndex": idx, "flag": curr_flag})
                # Synthetic yellow event from session marshal/player status context
                player_yellow = None
                try:
                    status_data = self.data.get("car_status", {}).get("carStatus", []) or []
                    if 0 <= self.player_car_index < len(status_data):
                        stat = status_data[self.player_car_index] if isinstance(status_data[self.player_car_index], dict) else {}
                        has_yellow = stat.get("hasYellowFlag")
                        if isinstance(has_yellow, bool):
                            player_yellow = has_yellow
                        else:
                            flag_color = str(stat.get("flagColor") or "").lower()
                            if flag_color:
                                player_yellow = "yellow" in flag_color
                except Exception:
                    player_yellow = None
                if isinstance(player_yellow, bool):
                    if player_yellow and self._last_player_yellow is not True:
                        self._emit_classified_event_locked(
                            "YELW",
                            "Yellow Flag",
                            {
                                "localPlayerYellow": True,
                                "immediateRisk": self._player_immediate_proximity_risk_locked(),
                            },
                            now,
                        )
                    self._last_player_yellow = player_yellow

                session_store.snapshot = new_snapshot
                self.data[packet_type] = session_store.to_dict()
            elif packet_type == "tyre_sets":
                self.data["tyre_sets"]["latest"] = data
            elif packet_type == "time_trial":
                self.data["time_trial"] = data
            elif packet_type == "lap_positions":
                self.data["lap_positions"] = data
            elif packet_type == "session_history":
                self.data["session_history"] = data
                car_idx = data.get("carIdx") if isinstance(data, dict) else None
                if isinstance(car_idx, int) and 0 <= car_idx < self.max_cars:
                    self.session_history_by_car[car_idx] = dict(data)
            else:
                self.data[packet_type] = data
            self.last_update = now

            # Update histories per packet type
            if packet_type == "motion":
                # Append sample to the current lap bucket (player only)
                player_idx = self.player_car_index
                # Determine current player lap from latest lap_data
                try:
                    laps = self.data.get("lap_data", {}).get("laps", []) or []
                    curr_lap = None
                    if isinstance(laps, list) and 0 <= player_idx < len(laps):
                        lap_entry = laps[player_idx]
                        if isinstance(lap_entry, dict):
                            curr_lap = lap_entry.get("currentLapNum")
                except Exception:
                    curr_lap = None
                motion = self.data.get("motion", {})
                history = motion.get("historyByLap")
                if not isinstance(history, list):
                    history = []
                    motion["historyByLap"] = history
                # Start a new lap bucket if needed (most recent first)
                if not history or history[0].get("lapNum") != curr_lap:
                    history.insert(0, {"lapNum": curr_lap, "samples": []})
                    # Trim to last N laps
                    del history[self.buffer_sizes["motion_laps"]:]
                # Build a sample for the player
                try:
                    cars = motion.get("cars", []) or []
                    car_sample = cars[player_idx] if 0 <= player_idx < len(cars) else None
                except Exception:
                    car_sample = None
                sample = {
                    "time": now,
                    "playerCar": car_sample,
                    "playerExtra": motion.get("playerExtra", {}),
                }
                # Append to current lap bucket
                history[0]["samples"].append(sample)
                motion_limit = self.buffer_sizes.get("motion_samples", 0)
                if motion_limit and len(history[0]["samples"]) > motion_limit:
                    del history[0]["samples"][
                        : len(history[0]["samples"]) - motion_limit
                    ]

            if packet_type == "car_telemetry":
                cars = data.get("carTelemetry", []) or []
                for idx, tel in enumerate(cars):
                    try:
                        self.car_history.car_telemetry[idx].append({"time": now, "data": dict(tel)})
                    except Exception:
                        # Be robust against unexpected structures
                        self.car_history.car_telemetry[idx].append({"time": now, "data": tel})

            elif packet_type == "car_status":
                cars = data.get("carStatus", []) or []
                watch_keys = {
                    "fuelPercentage",
                    "fuelRemainingLaps",
                    "fuelMixName",
                    "fuelCritical",
                    "ersPercentage",
                    "ersDeployModeName",
                    "actualTyreCompoundName",
                    "tyresAgeLaps",
                    "tyresOld",
                    "drsAvailable",
                    "flagColor",
                    "hasYellowFlag",
                    "hasRedFlag",
                }
                for idx, stat in enumerate(cars):
                    snap = {k: stat.get(k) for k in watch_keys if k in stat}
                    # If no watch keys found, fall back to full snapshot
                    if not snap:
                        snap = dict(stat)
                    dq = self.car_history.car_status[idx]
                    should_append = True
                    if dq:
                        last = dq[-1].get("data", {})
                        # Append only if something changed in watched keys
                        should_append = any(last.get(k) != snap.get(k) for k in snap.keys())
                    if should_append:
                        dq.append({"time": now, "data": snap})

            elif packet_type == "car_damage":
                cars = data.get("carDamage", []) or []
                for idx, dmg in enumerate(cars):
                    dq = self.car_history.car_damage[idx]
                    increased = False
                    prev = dq[-1]["data"] if dq else {}

                    def num_increased(prev_val, curr_val) -> bool:
                        try:
                            if isinstance(curr_val, (list, tuple)):
                                return any((curr_val[i] if i < len(curr_val) else 0) > (prev_val[i] if isinstance(prev_val, (list, tuple)) and i < len(prev_val) else 0) for i in range(len(curr_val)))
                            # Treat missing prev as 0
                            pv = prev_val if isinstance(prev_val, (int, float)) else 0
                            cv = curr_val if isinstance(curr_val, (int, float)) else pv
                            return cv > pv
                        except Exception:
                            return False

                    for k, v in (dmg or {}).items():
                        if isinstance(v, (int, float, list, tuple)):
                            if num_increased(prev.get(k), v):
                                increased = True
                                break
                    if increased:
                        dq.append({"time": now, "data": dict(dmg) if isinstance(dmg, dict) else dmg})

            elif packet_type == "lap_data":
                # Always set latest
                laps = data.get("laps", []) or []
                self.data["lap_data"]["laps"] = laps

                # Ensure per-car history structure exists
                if "history" not in self.data["lap_data"] or not isinstance(self.data["lap_data"].get("history"), list):
                    self.data["lap_data"]["history"] = [[] for _ in range(len(laps) or 22)]
                history = self.data["lap_data"]["history"]
                # Resize history if car count changes
                if len(history) < len(laps):
                    history.extend([[] for _ in range(len(laps) - len(history))])
                elif len(history) > len(laps) and len(laps) > 0:
                    history[:] = history[: len(laps)]

                # Ensure global events containers exist
                if "positionChanges" not in self.data["lap_data"]:
                    self.data["lap_data"]["positionChanges"] = []
                if "pitEvents" not in self.data["lap_data"]:
                    self.data["lap_data"]["pitEvents"] = []
                pos_changes = self.data["lap_data"]["positionChanges"]
                pit_events = self.data["lap_data"]["pitEvents"]

                for idx, lap in enumerate(laps):
                    if not isinstance(lap, dict):
                        continue
                    # Detect completed laps
                    curr = lap.get("currentLapNum")
                    try:
                        curr_num = int(curr) if curr is not None else None
                    except Exception:
                        curr_num = None
                    if curr_num is not None and curr_num > self._last_lap_num[idx]:
                        lap_num_completed = curr_num - 1 if curr_num > 0 else 0
                        entry = {
                            "time": now,
                            "lapNum": lap_num_completed,
                            "lapTimeFormatted": lap.get("lastLapTimeFormatted"),
                            "sector1": lap.get("sector1TimeFormatted"),
                            "sector2": lap.get("sector2TimeFormatted"),
                            "sector3": lap.get("sector3TimeFormatted"),
                            "invalid": lap.get("invalidLap", False),
                            "penalties": lap.get("penaltiesFormatted"),
                            "pitStatus": lap.get("pitStatusName"),
                            "positionAtFinish": lap.get("carPosition"),
                        }
                        # Append and trim per-car ring buffer
                        history[idx].insert(0, entry)
                        del history[idx][self.buffer_sizes["lap_history"]:]
                        self._last_lap_num[idx] = curr_num

                    # Detect position changes
                    try:
                        pos = int(lap.get("carPosition")) if lap.get("carPosition") is not None else 0
                    except Exception:
                        pos = 0
                    if pos and self._last_position[idx] and pos != self._last_position[idx]:
                        pos_changes.insert(0, {
                            "time": now,
                            "carIndex": idx,
                            "fromPos": self._last_position[idx],
                            "toPos": pos,
                            "lapNum": curr_num,
                        })
                        del pos_changes[self.buffer_sizes["position_changes"]:]
                    if pos:
                        self._last_position[idx] = pos

                    # Detect pit enter/exit
                    pit_name = lap.get("pitStatusName")
                    pit_flag = None
                    if isinstance(pit_name, str):
                        pit_flag = pit_name.lower() == "pitting"
                    elif pit_name is not None:
                        # numeric or other representations: treat non-zero as pitting
                        try:
                            pit_flag = int(pit_name) == 1
                        except Exception:
                            pit_flag = None
                    prev_pit = self._last_pit_status[idx]
                    if pit_flag is not None and prev_pit is not None and pit_flag != prev_pit:
                        pit_events.insert(0, {
                            "time": now,
                            "carIndex": idx,
                            "lapNum": curr_num,
                            "type": "enter" if pit_flag else "exit",
                        })
                        del pit_events[self.buffer_sizes["pit_events"]:]
                    if pit_flag is not None:
                        self._last_pit_status[idx] = pit_flag

            elif packet_type == "car_setups":
                setups = data.get("carSetups", []) or []
                for idx, setup in enumerate(setups):
                    dq = self.car_history.car_setups[idx]
                    snap = dict(setup) if isinstance(setup, dict) else setup
                    should_append = True
                    if dq:
                        last = dq[-1].get("data")
                        should_append = last != snap
                    if should_append:
                        dq.append({"time": now, "data": snap})

            elif packet_type == "session":
                # History now kept inside self.data["session"]["changes"], no external history buffer update needed
                pass
        
        pass
