#!/usr/bin/env python3
"""
F1 Telemetry MCP Server (FastMCP)

An MCP server that provides live F1 22 telemetry data through standardized tools.
This server captures UDP telemetry from F1 22 and exposes it via FastMCP.
"""

import json
import os
import socket
import threading
import time
from typing import Dict, Any, Optional, List
from collections import deque
import logging

# FastMCP imports
from fastmcp import FastMCP

# F1 telemetry imports
from packet_parsers import (
    PacketHeader,
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
)

from constants import EVENT_CODES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Packet type mappings
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
        
        # Telemetry data storage (latest snapshots)
        self.data = {
            "session": {
                # flattened latest fields go here as before
                # plus bounded histories below
                "changes": [],
                "forecastLatest": None,
                "forecastHistory": [],
                "safetyPeriods": [],
                "marshalZones": {"latest": [], "changes": []},
            },
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
            "final_classification": None,
            "session_history": None
        }

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

        # History buffers
        max_cars = 22
        self.history = {
            "car_telemetry": [deque(maxlen=self.buffer_sizes["car_telemetry"]) for _ in range(max_cars)],
            "car_status": [deque(maxlen=self.buffer_sizes["car_status"]) for _ in range(max_cars)],
            "car_damage": [deque(maxlen=self.buffer_sizes["car_damage"]) for _ in range(max_cars)],
            "car_setups": [deque(maxlen=self.buffer_sizes["car_setups"]) for _ in range(max_cars)],
            "session": deque(maxlen=self.buffer_sizes["session"]),
        }
        # Track last seen states per car
        self._last_lap_num = [0 for _ in range(max_cars)]
        self._last_position = [0 for _ in range(max_cars)]
        self._last_pit_status = [None for _ in range(max_cars)]
        
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
                    if hdr.m_packetFormat != 2022 and self.format_mismatch != hdr.m_packetFormat:
                        self.format_mismatch = hdr.m_packetFormat
                        logger.warning(f"Packet format {hdr.m_packetFormat} differs from expected 2022; decoders may be incompatible")
                    self.last_header = {
                        "format": hdr.m_packetFormat,
                        "packetVersion": getattr(hdr, "m_packetVersion", None),
                        "packetId": pid,
                        "sessionUID": getattr(hdr, "m_sessionUID", None),
                        "sessionTime": getattr(hdr, "m_sessionTime", None),
                        "frame": getattr(hdr, "m_frameIdentifier", None),
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
            elif packet_type == "session":
                prev = self.data.get("session") or {}
                # Preserve histories
                changes = list(prev.get("changes", []))
                forecast_latest = prev.get("forecastLatest")
                forecast_history = list(prev.get("forecastHistory", []))
                safety_periods = list(prev.get("safetyPeriods", []))
                marshal = prev.get("marshalZones") or {"latest": [], "changes": []}
                marshal_changes = list(marshal.get("changes", []))
                prev_latest = dict(prev)
                # Remove history keys from prev_latest for clean field compare
                for k in ("changes", "forecastLatest", "forecastHistory", "safetyPeriods", "marshalZones"):
                    prev_latest.pop(k, None)

                # Build new session snapshot
                new_session = {}
                if isinstance(data, dict):
                    new_session.update(data)

                # Safety car periods (based on name if present)
                prev_sc = prev_latest.get("safetyCarStatusName")
                curr_sc = new_session.get("safetyCarStatusName")
                if curr_sc != prev_sc:
                    # End any open period when moving to None
                    if prev_sc and prev_sc.lower() in ("vsc", "virtual safety car", "sc", "safety car") and (not curr_sc or curr_sc.lower() == "none"):
                        # Close the last open period
                        for sp in reversed(safety_periods):
                            if sp.get("endTime") is None:
                                sp["endTime"] = now
                                break
                    # Start a new period
                    if curr_sc and curr_sc.lower() in ("vsc", "virtual safety car", "sc", "safety car"):
                        sp_type = "VSC" if "vsc" in curr_sc.lower() else "SC"
                        safety_periods.append({"type": sp_type, "startTime": now, "endTime": None})

                # Changes ring buffer on key deltas
                watch_keys = [
                    "weatherName",
                    "trackTemperature",
                    "airTemperature",
                    "sessionTypeName",
                    "safetyCarStatusName",
                    "drsAllowed",
                ]
                change_snap = {k: new_session.get(k) for k in watch_keys if k in new_session}
                if change_snap:
                    should_append = True
                    if changes:
                        last = changes[0].get("data", {})
                        should_append = any(last.get(k) != change_snap.get(k) for k in change_snap.keys())
                    if should_append:
                        changes.insert(0, {"time": now, "data": change_snap})
                        del changes[self.buffer_sizes["session"]:]

                # Forecast tracking (support several possible keys)
                forecast_samples = None
                for key in ("forecastSamples", "weatherForecast", "forecast", "forecast_data"):
                    if key in new_session:
                        forecast_samples = new_session.get(key)
                        break
                if forecast_samples is not None:
                    forecast_latest = forecast_samples
                    # Only append if changed vs last snapshot (shallow compare)
                    should_fhist = True
                    if forecast_history:
                        last_samples = forecast_history[0].get("samples")
                        should_fhist = last_samples != forecast_samples
                    if should_fhist:
                        forecast_history.insert(0, {"time": now, "samples": forecast_samples})
                        del forecast_history[self.buffer_sizes["forecast"]:]

                # Marshal zones latest and changes
                marshal_latest = None
                for key in ("marshalZones", "marshalZonesFlags"):
                    if key in new_session:
                        marshal_latest = new_session.get(key)
                        break
                if marshal_latest is not None:
                    # detect per-zone changes if structure is list-like
                    try:
                        prev_m_latest = marshal.get("latest", []) or []
                        if isinstance(marshal_latest, list):
                            for idx, zone in enumerate(marshal_latest):
                                curr_flag = None
                                if isinstance(zone, dict):
                                    curr_flag = zone.get("flagColor") or zone.get("zoneFlagName") or zone.get("flag")
                                else:
                                    curr_flag = zone
                                prev_flag = None
                                if idx < len(prev_m_latest):
                                    pz = prev_m_latest[idx]
                                    prev_flag = pz.get("flagColor") or pz.get("zoneFlagName") or pz.get("flag") if isinstance(pz, dict) else pz
                                if curr_flag != prev_flag:
                                    marshal_changes.insert(0, {"time": now, "zoneIndex": idx, "flag": curr_flag})
                                    del marshal_changes[self.buffer_sizes["marshal"]:]
                        marshal = {"latest": marshal_latest, "changes": marshal_changes}
                    except Exception:
                        marshal = {"latest": marshal_latest, "changes": marshal_changes}

                # Assemble and store
                new_session["changes"] = changes
                new_session["forecastLatest"] = forecast_latest
                new_session["forecastHistory"] = forecast_history
                new_session["safetyPeriods"] = safety_periods
                new_session["marshalZones"] = marshal
                self.data[packet_type] = new_session
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
                        self.history["car_telemetry"][idx].append({"time": now, "data": dict(tel)})
                    except Exception:
                        # Be robust against unexpected structures
                        self.history["car_telemetry"][idx].append({"time": now, "data": tel})

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
                    dq = self.history["car_status"][idx]
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
                    dq = self.history["car_damage"][idx]
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
                    dq = self.history["car_setups"][idx]
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

    def _get_car_id_by_position(self, laps: List[Dict[str, Any]], position: Optional[int]) -> Optional[int]:
        if position is None:
            return None
        for idx, lap in enumerate(laps):
            if lap.get("carPosition") == position:
                return idx
        return None

    # Session helpers
    def get_current_weather(self) -> Dict[str, Any]:
        with self.lock:
            session = dict(self.data.get("session", {}))
        return {
            "weatherName": session.get("weatherName", "Unknown"),
            "trackTemperature": session.get("trackTemperature"),
            "airTemperature": session.get("airTemperature"),
            "lastUpdate": self.last_update,
        }

    def get_weather_forecast(self) -> Dict[str, Any]:
        with self.lock:
            session = dict(self.data.get("session", {}))
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
        with self.lock:
            total = self.data.get("session", {}).get("totalLaps")
        return total

    def get_current_track(self) -> str:
        with self.lock:
            track = self.data.get("session", {}).get("trackName")
        return track or "Unknown"

    def get_safety_car_status(self) -> Optional[str]:
        with self.lock:
            status = self.data.get("session", {}).get("safetyCarStatusName")
        return status

    def get_pitstop_window_recommendation(self) -> Dict[str, Optional[int]]:
        with self.lock:
            session = self.data.get("session", {})
            ideal = session.get("pitStopWindowIdealLap")
            latest = session.get("pitStopWindowLatestLap")
        return {"idealLap": ideal, "latestLap": latest}

    def get_pitstop_rejoin_position(self) -> Optional[int]:
        with self.lock:
            position = self.data.get("session", {}).get("pitStopRejoinPosition")
        return position

    # Lap helpers
    def get_current_lap(self) -> Optional[int]:
        with self.lock:
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            car_index = self.player_car_index
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return lap.get("currentLapNum")

    def get_num_remaining_laps(self) -> Optional[int]:
        with self.lock:
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            session = self.data.get("session", {})
            car_index = self.player_car_index
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        current = lap.get("currentLapNum")
        total = session.get("totalLaps")
        if total is None or total <= 0 or current is None:
            return None
        remaining = total - current
        return remaining if remaining >= 0 else 0

    def get_penalties(self) -> Dict[str, Any]:
        with self.lock:
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            car_index = self.player_car_index
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return {
            "carIndex": car_index,
            "penaltiesFormatted": lap.get("penaltiesFormatted", "None"),
            "penaltiesSeconds": lap.get("penalties"),
            "unservedDriveThroughs": lap.get("numUnservedDriveThroughPens"),
            "unservedStopGos": lap.get("numUnservedStopGoPens"),
        }

    def get_penalties_by_player(self, name: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            participants = list(self.data.get("participants", {}).get("participants", []))
            laps = list(self.data.get("lap_data", {}).get("laps", []))
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
        with self.lock:
            participants = list(self.data.get("participants", {}).get("participants", []))
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            player_idx = self.player_car_index
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
        with self.lock:
            participants = list(self.data.get("participants", {}).get("participants", []))
            laps = list(self.data.get("lap_data", {}).get("laps", []))
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
        with self.lock:
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            participants = list(self.data.get("participants", {}).get("participants", []))
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
        with self.lock:
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            car_index = self.player_car_index
        lap = laps[car_index] if 0 <= car_index < len(laps) else {}
        return lap.get("safetyCarDelta")

    def get_player_name_by_position(self, position: int) -> Optional[str]:
        with self.lock:
            laps = list(self.data.get("lap_data", {}).get("laps", []))
            participants = list(self.data.get("participants", {}).get("participants", []))
        car_idx = self._get_car_id_by_position(laps, position)
        if car_idx is None:
            return None
        return self._display_name_from_participants(participants, car_idx)

    # Event helpers
    def get_fastest_lap_data(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            history = list(self.data.get("event", {}).get("eventHistory", []))
            participants = list(self.data.get("participants", {}).get("participants", []))
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
        with self.lock:
            history = list(self.data.get("event", {}).get("eventHistory", []))
            participants = list(self.data.get("participants", {}).get("participants", []))
        return self._collect_penalty_events(history, participants)

    def get_penalities_by_driver_name(self, name: str) -> List[Dict[str, Any]]:
        with self.lock:
            history = list(self.data.get("event", {}).get("eventHistory", []))
            participants = list(self.data.get("participants", {}).get("participants", []))
        events = self._collect_penalty_events(history, participants)
        needle = name.strip().lower()
        if not needle:
            return events
        return [evt for evt in events if needle in (evt.get("driverName") or "").lower()]

    def get_drs_status(self) -> Dict[str, Any]:
        with self.lock:
            car_index = self.player_car_index
            telemetry = list(self.data.get("car_telemetry", {}).get("carTelemetry", []))
            status = list(self.data.get("car_status", {}).get("carStatus", []))
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
        with self.lock:
            session = dict(self.data.get("session", {}))
            last_update = self.last_update
        return {
            "trackName": session.get("trackName", "Unknown"),
            "sessionTypeName": session.get("sessionTypeName", "Unknown"),
            "weatherName": session.get("weatherName", "Clear"),
            "trackTemperature": session.get("trackTemperature", 0),
            "airTemperature": session.get("airTemperature", 0),
            "sessionTimeLeftFormatted": session.get("sessionTimeLeftFormatted", "00:00"),
            "totalLaps": session.get("totalLaps", 0),
            "trackLengthKm": session.get("trackLengthKm", 0),
            "lastUpdate": last_update
        }
        
    def get_race_standings(self, limit: int = 22) -> List[Dict[str, Any]]:
        """Get current race standings with all drivers"""
        standings = []
        with self.lock:
            participants = list(self.data.get("participants", {}).get("participants", []))
            lap_data = list(self.data.get("lap_data", {}).get("laps", []))
            player_idx = self.player_car_index
        
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
        with self.lock:
            car_index = self.player_car_index
            tel_data = list(self.data.get("car_telemetry", {}).get("carTelemetry", []))
            status_data = list(self.data.get("car_status", {}).get("carStatus", []))
            damage_data = list(self.data.get("car_damage", {}).get("carDamage", []))
            last_update = self.last_update
        
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
        with self.lock:
            events = list(self.data.get("event", {}).get("eventHistory", []))
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
        with self.lock:
            laps = self.data.get("lap_data", {}).get("laps", []) or []
            tel = self.data.get("car_telemetry", {}).get("carTelemetry", []) or []
            player_idx = self.player_car_index
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
        with self.lock:
            car_index = self.player_car_index
            status_data = list(self.data.get("car_status", {}).get("carStatus", []))
        status = status_data[car_index] if car_index < len(status_data) else {}
        return {
            "carIndex": car_index,
            "fuelPercentage": status.get("fuelPercentage"),
            "fuelRemainingLaps": status.get("fuelRemainingLaps"),
            "fuelMixName": status.get("fuelMixName"),
            "fuelCritical": status.get("fuelCritical"),
        }

    def get_ers_status(self) -> Dict[str, Any]:
        with self.lock:
            car_index = self.player_car_index
            status_data = list(self.data.get("car_status", {}).get("carStatus", []))
        status = status_data[car_index] if car_index < len(status_data) else {}
        return {
            "carIndex": car_index,
            "ersPercentage": status.get("ersPercentage"),
            "ersDeployModeName": status.get("ersDeployModeName"),
        }

    def get_tyres_status(self) -> Dict[str, Any]:
        with self.lock:
            car_index = self.player_car_index
            status_data = list(self.data.get("car_status", {}).get("carStatus", []))
            tel_data = list(self.data.get("car_telemetry", {}).get("carTelemetry", []))
            dmg_data = list(self.data.get("car_damage", {}).get("carDamage", []))
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
        with self.lock:
            car_index = self.player_car_index
            dmg_data = list(self.data.get("car_damage", {}).get("carDamage", []))
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


# Initialize telemetry capture (defaults can be overridden in main)
telemetry_capture = F1TelemetryCapture()

# Create FastMCP server
mcp = FastMCP("F1 Telemetry Server")


@mcp.tool()
def get_session_info() -> Dict[str, Any]:
    """Get current F1 session information including track, weather, and session details.
    
    Returns:
        Dict containing track name, session type, weather conditions, temperatures, 
        session time remaining, total laps, and track length.
    """
    return telemetry_capture.get_session_info()


@mcp.tool()
def get_current_weather() -> Dict[str, Any]:
    """Return the latest weather name with the most recent air/track temperatures."""
    return telemetry_capture.get_current_weather()


@mcp.tool()
def get_weather_forecast() -> Dict[str, Any]:
    """Return the latest forecast samples and the stored history."""
    return telemetry_capture.get_weather_forecast()


@mcp.tool()
def get_total_laps() -> Optional[int]:
    """Return the total laps scheduled for this session."""
    return telemetry_capture.get_total_laps()


@mcp.tool()
def get_current_track() -> str:
    """Return the current track name."""
    return telemetry_capture.get_current_track()


@mcp.tool()
def get_safety_car_status() -> Optional[str]:
    """Return the current safety car status name."""
    return telemetry_capture.get_safety_car_status()


@mcp.tool()
def get_pitstop_window_recommendation() -> Dict[str, Optional[int]]:
    """Return the ideal/latest lap window for pitstops."""
    return telemetry_capture.get_pitstop_window_recommendation()


@mcp.tool()
def get_pitstop_rejoin_position() -> Optional[int]:
    """Return the expected rejoin position after a pitstop."""
    return telemetry_capture.get_pitstop_rejoin_position()


@mcp.tool()
def get_race_standings(limit: int = 22) -> List[Dict[str, Any]]:
    """Get current race standings with all drivers, positions, and timing data.
    
    Args:
        limit: Maximum number of drivers to return (default: 22)
        
    Returns:
        List of driver information including position, name, team, lap times, 
        sector times, status, and penalties.
    """
    return telemetry_capture.get_race_standings(limit)


@mcp.tool()
def get_player_telemetry() -> Dict[str, Any]:
    """Get comprehensive telemetry data for the player's car.
    
    Returns:
        Dict containing detailed telemetry (speed, RPM, temperatures), 
        car status (fuel, ERS, tyres), and damage information.
    """
    return telemetry_capture.get_player_telemetry()


@mcp.tool()
def get_recent_events(limit: int = 5) -> List[Dict[str, Any]]:
    """Get recent race events like penalties, fastest laps, retirements, etc.
    
    Args:
        limit: Maximum number of events to return (default: 5)
        
    Returns:
        List of recent race events with timestamps and details.
    """
    return telemetry_capture.get_recent_events(limit)


@mcp.tool()
def get_current_lap() -> Optional[int]:
    """Return the player's current lap number."""
    return telemetry_capture.get_current_lap()


@mcp.tool()
def get_num_remaining_laps() -> Optional[int]:
    """Return how many laps remain for the player (if available)."""
    return telemetry_capture.get_num_remaining_laps()


@mcp.tool()
def get_penalties() -> Dict[str, Any]:
    """Return the player's pending penalties."""
    return telemetry_capture.get_penalties()


@mcp.tool()
def get_penalties_by_player(name: str) -> Optional[Dict[str, Any]]:
    """Return penalty info for a player name match."""
    return telemetry_capture.get_penalties_by_player(name)


@mcp.tool()
def get_teammate_position() -> Optional[Dict[str, Any]]:
    """Return the teammate's position details."""
    return telemetry_capture.get_teammate_position()


@mcp.tool()
def get_player_position_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get leaderboard info for a driver name match."""
    return telemetry_capture.get_player_position_by_name(name)


@mcp.tool()
def get_all_grid_positions() -> List[Dict[str, Any]]:
    """Return every driver name and position."""
    return telemetry_capture.get_all_grid_positions()


@mcp.tool()
def get_safety_car_delta() -> Optional[float]:
    """Return the safety car delta for the player."""
    return telemetry_capture.get_safety_car_delta()


@mcp.tool()
def get_player_name_by_position(position: int) -> Optional[str]:
    """Return the driver name occupying the supplied position."""
    return telemetry_capture.get_player_name_by_position(position)


@mcp.tool()
def get_fastest_lap_data() -> Optional[Dict[str, Any]]:
    """Return the most recent fastest lap event data."""
    return telemetry_capture.get_fastest_lap_data()


@mcp.tool()
def get_penalities() -> List[Dict[str, Any]]:
    """Return the list of penalty events in the current session."""
    return telemetry_capture.get_penalities()


@mcp.tool()
def get_penalities_by_driver_name(name: str) -> List[Dict[str, Any]]:
    """Return penalty events filtered by a driver name."""
    return telemetry_capture.get_penalities_by_driver_name(name)


@mcp.tool()
def get_drs_status() -> Dict[str, Any]:
    """Return the player's DRS status and availability."""
    return telemetry_capture.get_drs_status()

@mcp.tool()
def get_driver_by_position(position: int) -> Optional[Dict[str, Any]]:
    """Get detailed information about a driver by their current race position.
    
    Args:
        position: Race position (1-22)
        
    Returns:
        Driver information dict or None if position not found.
    """
    return telemetry_capture.get_driver_by_position(position)


@mcp.tool()
def get_driver_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Search for a driver by name (supports partial matching).
    
    Args:
        name: Driver name or partial name to search for
        
    Returns:
        Driver information dict or None if not found.
    """
    return telemetry_capture.get_driver_by_name(name)


@mcp.tool()
def get_top_drivers(count: int = 5) -> List[Dict[str, Any]]:
    """Get the top N drivers in the current race standings.
    
    Args:
        count: Number of top drivers to return (default: 5)
        
    Returns:
        List of top drivers with their current information.
    """
    standings = telemetry_capture.get_race_standings()
    return standings[:count]


@mcp.tool()
def get_race_summary() -> Dict[str, Any]:
    """Get a comprehensive race summary including session info, top 5 drivers, 
    player status, and recent events.
    
    Returns:
        Dict containing complete race overview.
    """
    return {
        "session": telemetry_capture.get_session_info(),
        "topDrivers": telemetry_capture.get_race_standings(5),
        "playerCar": telemetry_capture.get_player_telemetry(),
        "recentEvents": telemetry_capture.get_recent_events(3)
    }


@mcp.tool()
def get_capture_stats() -> Dict[str, Any]:
    """Debug: capture stats (packet counts, last header, errors)."""
    return telemetry_capture.get_capture_stats()


@mcp.tool()
def get_current_position() -> Optional[Dict[str, Any]]:
    """Get the player's current race position and info."""
    return telemetry_capture.get_current_position()


@mcp.tool()
def get_gap_to_driver_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Approximate gap to a driver by name (meters/laps/seconds)."""
    return telemetry_capture.get_gap_to_driver_by_name(name)


@mcp.tool()
def get_gap_to_driver_by_position(position: int) -> Optional[Dict[str, Any]]:
    """Approximate gap to a driver by race position."""
    return telemetry_capture.get_gap_to_driver_by_position(position)


@mcp.tool()
def get_gap_to_driver_in_front() -> Optional[Dict[str, Any]]:
    """Approximate gap to the car ahead of the player."""
    return telemetry_capture.get_gap_to_driver_in_front()


@mcp.tool()
def get_gap_to_driver_in_back() -> Optional[Dict[str, Any]]:
    """Approximate gap to the car behind the player."""
    return telemetry_capture.get_gap_to_driver_in_back()


@mcp.tool()
def get_fuel_status() -> Dict[str, Any]:
    """Fuel percentage, laps remaining, mix, and critical flag for the player."""
    return telemetry_capture.get_fuel_status()


@mcp.tool()
def get_ers_status() -> Dict[str, Any]:
    """ERS percentage and deploy mode for the player."""
    return telemetry_capture.get_ers_status()


@mcp.tool()
def get_tyres_status() -> Dict[str, Any]:
    """Tyre compound, age, temps, pressures, and wear for the player."""
    return telemetry_capture.get_tyres_status()


@mcp.tool()
def get_damage_status() -> Dict[str, Any]:
    """Player car damage summary."""
    return telemetry_capture.get_damage_status()


@mcp.tool()
def get_car_telemetry_history(car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent telemetry samples for a specific car.

    Args:
        car_index: Car index (0-21)
        limit: Max number of samples to return (default: 50)

    Returns:
        List of {time, data} entries, most recent first.
    """
    with telemetry_capture.lock:
        dq = telemetry_capture.history.get("car_telemetry", [])
        if 0 <= car_index < len(dq):
            items = list(dq[car_index])
        else:
            items = []
    return list(reversed(items[-limit:]))


@mcp.tool()
def get_car_status_changes(car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent car status change snapshots for a specific car.

    Args:
        car_index: Car index (0-21)
        limit: Max number of entries to return (default: 50)

    Returns:
        List of {time, data} entries, most recent first.
    """
    with telemetry_capture.lock:
        dq = telemetry_capture.history.get("car_status", [])
        if 0 <= car_index < len(dq):
            items = list(dq[car_index])
        else:
            items = []
    return list(reversed(items[-limit:]))


@mcp.tool()
def get_car_damage_events(car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent car damage increase events for a specific car.

    Args:
        car_index: Car index (0-21)
        limit: Max number of entries to return (default: 50)

    Returns:
        List of {time, data} entries, most recent first.
    """
    with telemetry_capture.lock:
        dq = telemetry_capture.history.get("car_damage", [])
        if 0 <= car_index < len(dq):
            items = list(dq[car_index])
        else:
            items = []
    return list(reversed(items[-limit:]))


@mcp.tool()
def get_car_lap_history(car_index: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent per-lap summaries for a specific car.

    Args:
        car_index: Car index (0-21)
        limit: Max number of laps to return (default: 50)

    Returns:
        List of per-lap summaries, most recent first.
    """
    with telemetry_capture.lock:
        lap_data = telemetry_capture.data.get("lap_data", {})
        hist = lap_data.get("history", []) or []
        items = hist[car_index] if 0 <= car_index < len(hist) else []
    # Stored most-recent first; slice up to limit
    return items[:limit]


@mcp.tool()
def get_session_changes(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent session-level changes (weather, temps, type).

    Args:
        limit: Max number of entries to return (default: 50)

    Returns:
        List of {time, data} entries, most recent first.
    """
    with telemetry_capture.lock:
        sess = telemetry_capture.data.get("session", {})
        changes = list(sess.get("changes", []))
    # changes are stored most-recent first; return up to limit
    return changes[:limit]


@mcp.tool()
def get_session_forecast(limit: int = 10) -> Dict[str, Any]:
    """Get session weather forecast: latest snapshot and recent history.

    Args:
        limit: Maximum number of historical forecast snapshots to return (default: 10)

    Returns:
        Dict with keys:
        - latest: latest forecast samples (decoder-specific structure or None)
        - history: most-recent-first list of {time, samples} entries
    """
    with telemetry_capture.lock:
        sess = telemetry_capture.data.get("session", {})
        latest = sess.get("forecastLatest")
        hist = list(sess.get("forecastHistory", []))
    return {"latest": latest, "history": hist[:limit]}


@mcp.tool()
def get_safety_periods() -> List[Dict[str, Any]]:
    """Get recorded Safety Car and VSC periods for the current session.

    Returns:
        List of periods with shape: {type: "SC"|"VSC", startTime: float, endTime: float|None}
        In-progress periods have endTime = None.
    """
    with telemetry_capture.lock:
        sess = telemetry_capture.data.get("session", {})
        periods = list(sess.get("safetyPeriods", []))
    return periods

def main():
    """Main entry point for the F1 Telemetry MCP Server"""
    import argparse
    ap = argparse.ArgumentParser(description="F1 22 Telemetry MCP Server")
    ap.add_argument("--udp-ip", default=os.getenv("F1_UDP_IP", telemetry_capture.bind_ip), help="UDP bind IP for telemetry")
    ap.add_argument("--udp-port", type=int, default=int(os.getenv("F1_UDP_PORT", str(telemetry_capture.port))), help="UDP port for telemetry")
    ap.add_argument("--host", default=os.getenv("F1_MCP_HOST", "127.0.0.1"), help="MCP server host")
    ap.add_argument("--port", type=int, default=int(os.getenv("F1_MCP_PORT", "20915")), help="MCP server port")
    ap.add_argument("--events-buffer", type=int, default=int(os.getenv("F1_EVENTS_BUFFER", str(telemetry_capture.events_buffer_size))), help="Max number of events to keep in memory")
    args = ap.parse_args()

    # Apply configuration
    telemetry_capture.bind_ip = args.udp_ip
    telemetry_capture.port = args.udp_port
    telemetry_capture.events_buffer_size = max(1, args.events_buffer)

    # Start telemetry capture
    telemetry_capture.start_capture()

    try:
        # Run the FastMCP server
        # mcp.run(transport="http", host=args.host, port=args.port)
        mcp.run()
    finally:
        # Clean up
        telemetry_capture.stop_capture()


if __name__ == "__main__":
    main()
