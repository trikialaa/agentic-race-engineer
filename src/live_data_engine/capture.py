import logging
import os
import socket
import threading
import time
from collections import deque
from typing import Dict, Any, Optional, List, Tuple

from src.live_data_engine.cache import CarHistoryBuffers, SessionStore
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

        # Track last seen states per car
        self._last_lap_num = [0 for _ in range(self.max_cars)]
        self._last_position = [0 for _ in range(self.max_cars)]
        self._last_pit_status = [None for _ in range(self.max_cars)]
        
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
                    data, addr = self.sock.recvfrom(2048)
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
                if event_code and event_code != "NULL" and event_code != "BUTN":
                    event_entry = {
                        "code": event_code,
                        "eventName": EVENT_CODES.get(event_code, event_code),
                        "details": data.get("details", {}),
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

                session_store.snapshot = new_snapshot
                self.data[packet_type] = session_store.to_dict()
            elif packet_type == "tyre_sets":
                self.data["tyre_sets"]["latest"] = data
            elif packet_type == "time_trial":
                self.data["time_trial"] = data
            elif packet_type == "lap_positions":
                self.data["lap_positions"] = data
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
        
    # Helper utilities
    def _display_name_from_participants(
        self, participants: List[Dict[str, Any]], car_index: Optional[int]
    ) -> str:
        if car_index is None:
            return "Unknown"
        if 0 <= car_index < len(participants):
            participant = participants[car_index]
            return participant.get("displayName") or participant.get("driverName") or f"Car {car_index}"
        return f"Car {car_index}"

    def _find_car_index_by_name(self, name: str, participants: List[Dict[str, Any]]) -> Optional[int]:
        if not name:
            return None
        needle = name.strip().lower()
        if not needle:
            return None
        for participant in participants:
            candidate = (participant.get("displayName") or participant.get("driverName") or "").lower()
            if needle in candidate:
                return participant.get("carIndex")
        return None

    def _collect_penalty_events(
        self, history: List[Dict[str, Any]], participants: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        penalties = []
        for entry in history:
            if entry.get("code") != "PENA":
                continue
            details = entry.get("details", {})
            driver_idx = details.get("vehicleIdx")
            penalties.append({
                "time": entry.get("time"),
                "driverName": self._display_name_from_participants(participants, driver_idx),
                "penaltyType": details.get("penaltyTypeName"),
                "infringementType": details.get("infringementTypeName"),
                "lapNum": details.get("lapNum"),
                "placesGained": details.get("placesGained"),
                "raw": details,
            })
        return penalties

    def _session_snapshot(self) -> Dict[str, Any]:
        """Return a copy of the latest session payload (thread-safe)."""
        with self.lock:
            return dict(self.data.get("session", {}))

    def _session_snapshot_with_timestamp(self) -> Tuple[Dict[str, Any], float]:
        """Return the latest session payload along with the most recent update timestamp."""
        with self.lock:
            return dict(self.data.get("session", {})), self.last_update

    def _lap_participant_snapshot(self) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Snapshot lap data and participant list together with the player's car index."""
        with self.lock:
            return (
                self.player_car_index,
                list(self.data.get("lap_data", {}).get("laps", [])),
                list(self.data.get("participants", {}).get("participants", [])),
            )

    def _car_arrays_with_timestamp(self, *pairs: Tuple[str, str]) -> Tuple[int, List[List[Any]], float]:
        """Gather multiple per-car arrays while also returning the latest update timestamp."""
        with self.lock:
            idx = self.player_car_index
            arrays = [list(self.data.get(category, {}).get(key, [])) for category, key in pairs]
            timestamp = self.last_update
        return idx, arrays, timestamp

    def _car_arrays(self, *pairs: Tuple[str, str]) -> Tuple[int, List[List[Any]]]:
        """Gather multiple per-car arrays without the timestamp."""
        idx, arrays, _ = self._car_arrays_with_timestamp(*pairs)
        return idx, arrays

    def _event_history_snapshot(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return the latest event history and participant list under lock."""
        with self.lock:
            return (
                list(self.data.get("event", {}).get("eventHistory", [])),
                list(self.data.get("participants", {}).get("participants", [])),
            )

    def _get_car_id_by_position(self, laps: List[Dict[str, Any]], position: Optional[int]) -> Optional[int]:
        if position is None:
            return None
        for idx, lap in enumerate(laps):
            if lap.get("carPosition") == position:
                return idx
        return None

    # Session helpers
    def get_current_weather(self) -> Dict[str, Any]:
        session, last_update = self._session_snapshot_with_timestamp()
        return {
            "weatherName": session.get("weatherName", "Unknown"),
            "trackTemperature": session.get("trackTemperature"),
            "airTemperature": session.get("airTemperature"),
            "lastUpdate": last_update,
        }

    def get_weather_forecast(self) -> Dict[str, Any]:
        session = self._session_snapshot()
        forecast_samples = session.get("forecastLatest")
        if forecast_samples is None:
            forecast_samples = session.get("weatherForecast") or []
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

    def get_total_laps(self) -> Optional[int]:
        session = self._session_snapshot()
        return session.get("totalLaps")

    def get_current_track(self) -> str:
        session = self._session_snapshot()
        return session.get("trackName") or "Unknown"

    def get_safety_car_status(self) -> Optional[str]:
        session = self._session_snapshot()
        return session.get("safetyCarStatusName")

    def get_pitstop_window_recommendation(self) -> Dict[str, Optional[int]]:
        session = self._session_snapshot()
        return {
            "idealLap": session.get("pitStopWindowIdealLap"),
            "latestLap": session.get("pitStopWindowLatestLap"),
        }

    def get_pitstop_rejoin_position(self) -> Optional[int]:
        session = self._session_snapshot()
        return session.get("pitStopRejoinPosition")

    # Lap helpers
    def get_current_lap(self) -> Optional[int]:
        car_index, laps, _ = self._lap_participant_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return lap.get("currentLapNum")

    def get_num_remaining_laps(self) -> Optional[int]:
        car_index, laps, _ = self._lap_participant_snapshot()
        session = self._session_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        current = lap.get("currentLapNum")
        total = session.get("totalLaps")
        if total is None or total <= 0 or current is None:
            return None
        remaining = total - current
        return remaining if remaining >= 0 else 0

    def get_penalties(self) -> Dict[str, Any]:
        car_index, laps, _ = self._lap_participant_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return {
            "carIndex": car_index,
            "penaltiesFormatted": lap.get("penaltiesFormatted", "None"),
            "penaltiesSeconds": lap.get("penalties"),
            "unservedDriveThroughs": lap.get("numUnservedDriveThroughPens"),
            "unservedStopGos": lap.get("numUnservedStopGoPens"),
        }

    def get_penalties_by_player(self, name: str) -> Optional[Dict[str, Any]]:
        _, laps, participants = self._lap_participant_snapshot()
        car_index = self._find_car_index_by_name(name, participants)
        if car_index is None or car_index >= len(laps):
            return None
        lap = laps[car_index]
        return {
            "carIndex": car_index,
            "driverName": self._display_name_from_participants(participants, car_index),
            "penaltiesFormatted": lap.get("penaltiesFormatted", "None"),
            "penaltiesSeconds": lap.get("penalties"),
            "unservedDriveThroughs": lap.get("numUnservedDriveThroughPens"),
            "unservedStopGos": lap.get("numUnservedStopGoPens"),
        }

    def get_teammate_position(self) -> Optional[Dict[str, Any]]:
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

    def get_player_position_by_name(self, name: str) -> Optional[Dict[str, Any]]:
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

    def get_all_grid_positions(self) -> List[Dict[str, Any]]:
        _, laps, participants = self._lap_participant_snapshot()
        grid = []
        for idx, lap in enumerate(laps):
            position = lap.get("carPosition")
            if position is None or position == 0:
                continue
            grid.append({
                "position": position,
                "driverName": self._display_name_from_participants(participants, idx),
                "carIndex": idx,
            })
        grid.sort(key=lambda entry: entry["position"] or 999)
        return grid

    def get_safety_car_delta(self) -> Optional[float]:
        car_index, laps, _ = self._lap_participant_snapshot()
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return lap.get("safetyCarDelta")

    def get_player_name_by_position(self, position: int) -> Optional[str]:
        _, laps, participants = self._lap_participant_snapshot()
        car_idx = self._get_car_id_by_position(laps, position)
        if car_idx is None:
            return None
        return self._display_name_from_participants(participants, car_idx)

    # Event helpers
    def get_fastest_lap_data(self) -> Optional[Dict[str, Any]]:
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

    def get_penalities(self) -> List[Dict[str, Any]]:
        history, participants = self._event_history_snapshot()
        return self._collect_penalty_events(history, participants)

    def get_penalities_by_driver_name(self, name: str) -> List[Dict[str, Any]]:
        history, participants = self._event_history_snapshot()
        events = self._collect_penalty_events(history, participants)
        needle = name.strip().lower()
        if not needle:
            return events
        return [evt for evt in events if needle in (evt.get("driverName") or "").lower()]

    def get_drs_status(self) -> Dict[str, Any]:
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


    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information"""
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
        
    def get_race_standings(self, limit: int = 22) -> List[Dict[str, Any]]:
        """Get current race standings with all drivers"""
        standings = []
        player_idx, lap_data, participants = self._lap_participant_snapshot()
        
        for i in range(min(len(participants), len(lap_data), 22)):
            participant = participants[i]
            lap = lap_data[i]
            
            if participant.get("displayName") or participant.get("name"):
                driver_info = {
                    "carIndex": i,
                    "position": lap.get("carPosition", 0),
                    "driverName": participant.get("displayName", participant.get("name", "Unknown")),
                    "teamName": participant.get("teamName", "Unknown"),
                    "currentLap": lap.get("currentLapNum", 0),
                    "lastLapTime": lap.get("lastLapTimeFormatted", "0:00.000"),
                    "sector1Time": lap.get("sector1TimeFormatted", "00.000"),
                    "sector2Time": lap.get("sector2TimeFormatted", "00.000"),
                    "driverStatus": lap.get("driverStatusName", "Unknown"),
                    "resultStatus": lap.get("resultStatusName", "Unknown"),
                    "isPlayer": i == player_idx,
                    "penalties": lap.get("penaltiesFormatted", "None"),
                    "pitStatus": lap.get("pitStatusName", "None")
                }
                standings.append(driver_info)
                
        # Sort by position
        standings.sort(key=lambda x: x["position"] if x["position"] > 0 else 999)
        return standings[:limit]
        
    def get_player_telemetry(self) -> Dict[str, Any]:
        """Get detailed telemetry for the player's car"""
        car_index, arrays, last_update = self._car_arrays_with_timestamp(
            ("car_telemetry", "carTelemetry"),
            ("car_status", "carStatus"),
            ("car_damage", "carDamage"),
        )
        tel_data, status_data, damage_data = arrays
        
        # Get telemetry data
        telemetry = {}
        if tel_data:
            if car_index < len(tel_data):
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
                        "surface": tel.get("tyresSurfaceTemperature", [0,0,0,0]),
                        "inner": tel.get("tyresInnerTemperature", [0,0,0,0])
                    },
                    "brakeTemperatures": tel.get("brakesTemperature", [0,0,0,0]),
                    "warnings": {
                        "engine": tel.get("hasEngineWarning", False),
                        "brakes": tel.get("hasBrakeWarning", False),
                        "tyres": tel.get("hasTyreWarning", False)
                    }
                }
        
        # Get car status
        status = {}
        if status_data:
            if car_index < len(status_data):
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
                    "hasRedFlag": stat.get("hasRedFlag", False)
                }
        
        # Get damage info
        damage = {}
        if damage_data:
            if car_index < len(damage_data):
                dmg = damage_data[car_index]
                damage = {
                    "tyreWear": dmg.get("m_tyresWear", [0,0,0,0]),
                    "frontWingDamage": [dmg.get("m_frontLeftWingDamage", 0), dmg.get("m_frontRightWingDamage", 0)],
                    "rearWingDamage": dmg.get("m_rearWingDamage", 0),
                    "floorDamage": dmg.get("m_floorDamage", 0),
                    "diffuserDamage": dmg.get("m_diffuserDamage", 0)
                }
        
        return {
            "carIndex": car_index,
            "telemetry": telemetry,
            "status": status,
            "damage": damage,
            "lastUpdate": last_update
        }
        
    def get_recent_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent race events"""
        events, _ = self._event_history_snapshot()
        return events[:limit]
        
    def get_driver_by_position(self, position: int) -> Optional[Dict[str, Any]]:
        """Get driver information by race position"""
        standings = self.get_race_standings()
        return next((d for d in standings if d["position"] == position), None)
        
    def get_driver_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get driver information by name (partial match)"""
        standings = self.get_race_standings()
        name_lower = name.lower()
        return next((d for d in standings if name_lower in d["driverName"].lower()), None)
    
    def get_current_position(self) -> Optional[Dict[str, Any]]:
        """Return the player's current position and basic info."""
        standings = self.get_race_standings()
        return next((s for s in standings if s.get("isPlayer")), None)

    def _gap_to_car(self, target_car_index: int) -> Optional[Dict[str, Any]]:
        """Compute rough gap from player to target car using lap distances."""
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
            t_speed = (tel[target_car_index].get("speedKph") or 0) / 3.6 if target_car_index < len(tel) else 0
            avg_speed = max((p_speed + t_speed) / 2.0, 0.1)
            gap_seconds = gap_meters / avg_speed
        except Exception:
            gap_seconds = None
        return {
            "targetCarIndex": target_car_index,
            "gapMeters": gap_meters,
            "gapLaps": lap_diff,
            "gapSecondsApprox": gap_seconds,
        }

    def get_gap_to_driver_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        driver = self.get_driver_by_name(name)
        if not driver:
            return None
        return self._gap_to_car(driver["carIndex"])

    def get_gap_to_driver_by_position(self, position: int) -> Optional[Dict[str, Any]]:
        driver = self.get_driver_by_position(position)
        if not driver:
            return None
        return self._gap_to_car(driver["carIndex"])

    def get_gap_to_driver_in_front(self) -> Optional[Dict[str, Any]]:
        player = self.get_current_position()
        if not player:
            return None
        pos = player.get("position")
        if not pos or pos <= 1:
            return None
        return self.get_gap_to_driver_by_position(pos - 1)

    def get_gap_to_driver_in_back(self) -> Optional[Dict[str, Any]]:
        player = self.get_current_position()
        if not player:
            return None
        pos = player.get("position")
        if not pos:
            return None
        return self.get_gap_to_driver_by_position(pos + 1)

    def get_fuel_status(self) -> Dict[str, Any]:
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

    def get_ers_status(self) -> Dict[str, Any]:
        car_index, arrays = self._car_arrays(("car_status", "carStatus"))
        status_data = arrays[0]
        status = status_data[car_index] if car_index < len(status_data) else {}
        return {
            "carIndex": car_index,
            "ersPercentage": status.get("ersPercentage"),
            "ersDeployModeName": status.get("ersDeployModeName"),
        }

    def get_tyres_status(self) -> Dict[str, Any]:
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
            "compound": status.get("actualTyreCompoundName"),
            "ageLaps": status.get("tyresAgeLaps"),
            "tyresOld": status.get("tyresOld"),
            "surfaceTemp": tel.get("tyresSurfaceTemperature"),
            "innerTemp": tel.get("tyresInnerTemperature"),
            "pressures": tel.get("tyresPressure"),
            "wear": dmg.get("m_tyresWear"),
        }

    def get_damage_status(self) -> Dict[str, Any]:
        car_index, arrays = self._car_arrays(("car_damage", "carDamage"))
        dmg_data = arrays[0]
        dmg = dmg_data[car_index] if car_index < len(dmg_data) else {}
        return {
            "carIndex": car_index,
            "tyreWear": dmg.get("m_tyresWear"),
            "frontWingDamage": [dmg.get("m_frontLeftWingDamage"), dmg.get("m_frontRightWingDamage")],
            "rearWingDamage": dmg.get("m_rearWingDamage"),
            "floorDamage": dmg.get("m_floorDamage"),
            "diffuserDamage": dmg.get("m_diffuserDamage"),
            "drsFault": dmg.get("m_drsFault"),
        }
    
    def get_capture_stats(self) -> Dict[str, Any]:
        """Return basic capture stats for debugging"""
        with self.lock:
            counts = dict(self.packet_counts)
            unknown = self.unknown_packets
            errors = self.error_count
            last_hdr = dict(self.last_header) if isinstance(self.last_header, dict) else None
            last_err = self.last_error
        return {
            "packetCounts": counts,
            "unknownPackets": unknown,
            "errors": errors,
            "lastHeader": last_hdr,
            "lastError": last_err,
            "formatMismatch": self.format_mismatch,
        }


# Motion extras accessors
    def get_motion_ex(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.data.get("motion_ex") or {})

    def get_tyre_sets(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.data.get("tyre_sets", {}).get("latest")

    def get_time_trial_data(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.data.get("time_trial") or {})

    def get_lap_positions(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.data.get("lap_positions") or {})

    def get_car_telemetry_history(self, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            dq = []
            if 0 <= car_index < len(self.car_history.car_telemetry):
                dq = list(self.car_history.car_telemetry[car_index])
        return list(reversed(dq[-limit:]))

    def get_car_status_changes(self, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            dq = []
            if 0 <= car_index < len(self.car_history.car_status):
                dq = list(self.car_history.car_status[car_index])
        return list(reversed(dq[-limit:]))

    def get_car_damage_events(self, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            dq = []
            if 0 <= car_index < len(self.car_history.car_damage):
                dq = list(self.car_history.car_damage[car_index])
        return list(reversed(dq[-limit:]))

    def get_car_lap_history(self, car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            laps = self.data.get("lap_data", {}).get("history", [])
            entries = laps[car_index] if 0 <= car_index < len(laps) else []
        return entries[:limit]

    def get_session_changes(self, limit: int = 50) -> List[Dict[str, Any]]:
        session = self._session_snapshot()
        changes = session.get("changes", [])
        return changes[:limit]

    def get_session_forecast(self, limit: int = 10) -> Dict[str, Any]:
        session = self._session_snapshot()
        latest = session.get("forecastLatest")
        history = session.get("forecastHistory") or []
        return {"latest": latest, "history": history[:limit]}

    def get_safety_periods(self) -> List[Dict[str, Any]]:
        session = self._session_snapshot()
        return session.get("safetyPeriods", [])
