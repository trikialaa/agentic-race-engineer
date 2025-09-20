import socket
import curses
import json
import sys
import time
from dataclasses import asdict
from typing import Dict, Any
import struct

# Import packet parsers
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
    PACKET_ID
)

# Import constants
from constants import (
    WEATHER_TYPES,
    SESSION_TYPES,
    SURFACE_TYPES,
    TYRE_COMPOUNDS,
    ERS_DEPLOYMENT_MODES,
    FLAG_COLORS,
    RESULT_STATUS,
    DRIVER_STATUS,
    MAX_ERS_ENERGY,
    TEAM_NAMES
)

# All packet types
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




class TelemetryDisplay:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.packet_counts = {key: 0 for key in ["motion", "session", "lap_data", "event", "participants", 
                                               "car_setups", "car_telemetry", "car_status", "final_classification", 
                                               "lobby_info", "car_damage", "session_history"]}
        # Initialize base packet data structure
        self.data = {
            "motion": {
                "cars": [{
                    "worldPosition": [0, 0, 0],
                    "worldVelocity": [0, 0, 0],
                    "worldForwardDir": [0, 0, 0],
                    "worldRightDir": [0, 0, 0],
                    "gForces": [0, 0, 0],
                    "rotation": [0, 0, 0]
                }],
                "playerExtra": {
                    "suspensionPosition": [0, 0, 0, 0],
                    "suspensionVelocity": [0, 0, 0, 0],
                    "suspensionAcceleration": [0, 0, 0, 0],
                    "wheelSpeed": [0, 0, 0, 0],
                    "wheelSlip": [0, 0, 0, 0],
                    "localVelocity": [0, 0, 0],
                    "angularVelocity": [0, 0, 0],
                    "angularAcceleration": [0, 0, 0],
                    "frontWheelsAngle": 0
                }
            },
            "session": {
                "trackTemperature": 0,
                "airTemperature": 0,
                "weather": 0,
                "trackLength": 0,
                "sessionType": 0,
                "totalLaps": 0,
                "sessionTimeLeft": 0,
                "sessionDuration": 0,
                "pitSpeedLimit": 0,
                "gamePaused": 0,
                "isSpectating": 0,
                "spectatorCarIndex": 0,
                "marshalZones": [],
                "weatherForecast": []
            },
            "lap_data": {
                "laps": [{
                    "lastLapTimeInMS": 0,
                    "currentLapTimeInMS": 0,
                    "sector1TimeInMS": 0,
                    "sector2TimeInMS": 0,
                    "sector3TimeInMS": 0,
                    "carPosition": 0,
                    "currentLapNum": 0,
                    "driverStatus": 0,
                    "resultStatus": 0
                }]
            },
            "car_telemetry": {
                "carTelemetry": [{
                    "speedKph": 0,
                    "gear": 0,
                    "engineRPM": 0,
                    "throttle": 0,
                    "brake": 0,
                    "drs": 0,
                    "revLightsPercent": 0,
                    "tyresSurfaceTemperature": [0, 0, 0, 0],
                    "tyresInnerTemperature": [0, 0, 0, 0],
                    "brakesTemperature": [0, 0, 0, 0]
                }]
            },
            "car_status": {
                "carStatus": [{
                    "fuelInTank": 0,
                    "fuelCapacity": 0,
                    "fuelRemainingLaps": 0,
                    "fuelMix": 0,
                    "ersStoreEnergy": 0,
                    "ersDeployMode": 0,
                    "ersHarvestedThisLapMGUK": 0,
                    "ersHarvestedThisLapMGUH": 0,
                    "ersDeployedThisLap": 0,
                    "drsAllowed": 0,
                    "drsActivationDistance": 0,
                    "vehicleFiaFlags": -1,
                    "actualTyreCompound": 0,
                    "tyresAgeLaps": 0
                }]
            },
            "car_damage": {
                "carDamage": [{
                    "m_tyresWear": [0, 0, 0, 0],
                    "m_tyresDamage": [0, 0, 0, 0],
                    "m_frontLeftWingDamage": 0,
                    "m_frontRightWingDamage": 0,
                    "m_rearWingDamage": 0,
                    "m_floorDamage": 0,
                    "m_diffuserDamage": 0
                }]
            },
            "car_setups": {
                "carSetups": [{
                    "m_frontWing": 0,
                    "m_rearWing": 0,
                    "m_frontSuspension": 0,
                    "m_rearSuspension": 0,
                    "m_frontSuspensionHeight": 0,
                    "m_rearSuspensionHeight": 0,
                    "m_brakeBias": 0,
                    "m_brakePressure": 0,
                    "m_tyrePressure": [0, 0, 0, 0]
                }]
            },
            "participants": {
                "numActiveCars": 0,
                "participants": []
            },
            "event": {
                "eventStringCode": "",
                "eventDetails": {},
                "eventHistory": []  # List to store recent events
            },
            "lobby_info": {
                "lobbyPlayers": []
            },
            "final_classification": None,
            "session_history": None
        }
        # Initialize curses
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)    # Good condition
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # Warning
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)      # Critical
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)     # Headers
        curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)     # Info
        self.stdscr.nodelay(1)  # Non-blocking input
        
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.player_car_index = 0  # Initialize player car index
        self.packet_counts = {key: 0 for key in ["motion", "session", "lap_data", "event", "participants", 
                                               "car_setups", "car_telemetry", "car_status", "final_classification", 
                                               "lobby_info", "car_damage", "session_history"]}
        # Initialize base packet data structure
        self.data = {
            "motion": {
                "cars": [{
                    "worldPosition": [0, 0, 0],
                    "worldVelocity": [0, 0, 0],
                    "worldForwardDir": [0, 0, 0],
                    "worldRightDir": [0, 0, 0],
                    "gForces": [0, 0, 0],
                    "rotation": [0, 0, 0]
                }],
                "playerExtra": {
                    "suspensionPosition": [0, 0, 0, 0],
                    "suspensionVelocity": [0, 0, 0, 0],
                    "suspensionAcceleration": [0, 0, 0, 0],
                    "wheelSpeed": [0, 0, 0, 0],
                    "wheelSlip": [0, 0, 0, 0],
                    "localVelocity": [0, 0, 0],
                    "angularVelocity": [0, 0, 0],
                    "angularAcceleration": [0, 0, 0],
                    "frontWheelsAngle": 0
                }
            },
            "session": {
                "trackTemperature": 0,
                "airTemperature": 0,
                "weather": 0,
                "trackLength": 0,
                "sessionType": 0,
                "totalLaps": 0,
                "sessionTimeLeft": 0,
                "sessionDuration": 0,
                "pitSpeedLimit": 0,
                "gamePaused": 0,
                "isSpectating": 0,
                "spectatorCarIndex": 0,
                "marshalZones": [],
                "weatherForecast": []
            },
            "lap_data": {
                "laps": [{
                    "lastLapTimeInMS": 0,
                    "currentLapTimeInMS": 0,
                    "sector1TimeInMS": 0,
                    "sector2TimeInMS": 0,
                    "sector3TimeInMS": 0,
                    "carPosition": 0,
                    "currentLapNum": 0,
                    "driverStatus": 0,
                    "resultStatus": 0
                }]
            },
            "car_telemetry": {
                "carTelemetry": [{
                    "speedKph": 0,
                    "gear": 0,
                    "engineRPM": 0,
                    "throttle": 0,
                    "brake": 0,
                    "drs": 0,
                    "revLightsPercent": 0,
                    "tyresSurfaceTemperature": [0, 0, 0, 0],
                    "tyresInnerTemperature": [0, 0, 0, 0],
                    "brakesTemperature": [0, 0, 0, 0]
                }]
            },
            "car_status": {
                "carStatus": [{
                    "fuelInTank": 0,
                    "fuelCapacity": 0,
                    "fuelRemainingLaps": 0,
                    "fuelMix": 0,
                    "ersStoreEnergy": 0,
                    "ersDeployMode": 0,
                    "ersHarvestedThisLapMGUK": 0,
                    "ersHarvestedThisLapMGUH": 0,
                    "ersDeployedThisLap": 0,
                    "drsAllowed": 0,
                    "drsActivationDistance": 0,
                    "vehicleFiaFlags": -1,
                    "actualTyreCompound": 0,
                    "tyresAgeLaps": 0
                }]
            },
            "car_damage": {
                "carDamage": [{
                    "m_tyresWear": [0, 0, 0, 0],
                    "m_tyresDamage": [0, 0, 0, 0],
                    "m_frontLeftWingDamage": 0,
                    "m_frontRightWingDamage": 0,
                    "m_rearWingDamage": 0,
                    "m_floorDamage": 0,
                    "m_diffuserDamage": 0
                }]
            },
            "car_setups": {
                "carSetups": [{
                    "m_frontWing": 0,
                    "m_rearWing": 0,
                    "m_frontSuspension": 0,
                    "m_rearSuspension": 0,
                    "m_frontSuspensionHeight": 0,
                    "m_rearSuspensionHeight": 0,
                    "m_brakeBias": 0,
                    "m_brakePressure": 0,
                    "m_tyrePressure": [0, 0, 0, 0]
                }]
            },
            "participants": {
                "numActiveCars": 0,
                "participants": []
            },
            "event": {
                "eventStringCode": "",
                "eventDetails": {},
                "eventHistory": []  # List to store recent events
            },
            "lobby_info": {
                "lobbyPlayers": []
            },
            "final_classification": None,
            "session_history": None
        }
        # Initialize curses
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)    # Good condition
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # Warning
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)      # Critical
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)     # Headers
        curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)     # Info
        self.stdscr.nodelay(1)  # Non-blocking input

    def update_data(self, packet_type: str, data: Dict[str, Any], header: PacketHeader = None):
        """Update stored telemetry data"""
        self.packet_counts[packet_type] += 1
        
        # Update player car index if header is provided
        if header and hasattr(header, 'm_playerCarIndex'):
            self.player_car_index = header.m_playerCarIndex
        
        if packet_type == "event":
            # Keep track of the last 5 events
            event_code = data.get("eventCode", "")
            if event_code:
                # Convert from bytes if needed
                if isinstance(event_code, bytes):
                    event_code = event_code.decode('utf-8').strip()
                
                self.data[packet_type]["eventStringCode"] = event_code
                details = data.get("details", {})
                self.data[packet_type]["eventDetails"] = details
                
                # Only add non-null events to history
                if event_code and event_code != "NULL":
                    self.data[packet_type]["eventHistory"].insert(0, {
                        "code": event_code,
                        "details": details,
                        "time": time.strftime("%H:%M:%S")
                    })
                    # Keep only the last 5 non-null events
                    self.data[packet_type]["eventHistory"] = [
                        evt for evt in self.data[packet_type]["eventHistory"][:5]
                        if evt["code"] and evt["code"] != "NULL"
                    ]
        else:
            self.data[packet_type] = data
        
    def display_participants(self, start_y: int) -> int:
        """Display participants data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== PARTICIPANTS ===", header_attr)
        start_y += 1
        
        if "participants" in self.data["participants"]:
            max_y, _ = self.stdscr.getmaxyx()
            participants_per_column = min((max_y - start_y - 2) // 2, 10)  # Show up to 10 per column, 2 columns
            total_shown = participants_per_column * 2  # Show in 2 columns

            for i, p in enumerate(self.data["participants"]["participants"]):
                if i >= total_shown:  # Maximum participants to show
                    break
                if p.get("name", ""):  # Only show active participants
                    name = p["name"] if isinstance(p["name"], str) else p["name"].decode('utf-8').strip()
                    number = p.get("raceNumber", 0)
                    team_id = p.get("teamId", 0)
                    team_name = TEAM_NAMES.get(team_id, f"Team {team_id}")
                    ai = p.get("aiControlled", False)
                    nationality = p.get("nationality", 0)
                    network_id = p.get("networkId", "")
                    
                    # Calculate position for 2-column layout
                    row = i % participants_per_column
                    col = i // participants_per_column * 60  # 60 characters per column
                    
                    self.stdscr.addstr(start_y + row, col, 
                        f"#{number:2d} | {name:<16} | {team_name:<14} | AI: {'Y' if ai else 'N'}")
                    
            start_y += participants_per_column + 1  # Account for header + rows
        
        # Show lobby info if available
        if self.data["lobby_info"] and "lobbyPlayers" in self.data["lobby_info"]:
            lobby = self.data["lobby_info"]
            self.stdscr.addstr(start_y, 0, "=== LOBBY INFO ===", header_attr)
            start_y += 1
            
            for i, player in enumerate(lobby["lobbyPlayers"]):
                if i >= 5:  # Show only first 5 lobby players to save space
                    break
                    
                name = player.get("m_name", "").decode('utf-8').strip()
                ready = "Ready" if player.get("m_readyStatus", 0) == 1 else "Not Ready"
                nat = player.get("m_nationality", 0)
                
                ready_color = curses.color_pair(1) if ready == "Ready" else curses.color_pair(2)
                self.stdscr.addstr(start_y + i, 0, f"{name:<20} | ")
                self.stdscr.addstr(f"{ready:<9}", ready_color)
                
            start_y += 6  # Header + 5 players
            
        return start_y

    def display_car_status(self, start_y: int) -> int:
        """Display car status data"""
        self.stdscr.addstr(start_y, 0, "=== CAR STATUS (Player) ===", curses.A_BOLD | curses.color_pair(5))
        start_y += 1
        
        if "carStatus" in self.data["car_status"]:
            car_index = min(self.player_car_index, len(self.data["car_status"]["carStatus"]) - 1)
            car = self.data["car_status"]["carStatus"][car_index]  # Player's car            # Fuel stats
            fuel_mix_modes = {0: "Lean", 1: "Standard", 2: "Rich", 3: "Max"}
            fuel_mix = fuel_mix_modes.get(car.get('fuelMix', 0), "Unknown")
            self.stdscr.addstr(start_y, 0, 
                f"Fuel: {car.get('fuelInTank', 0):.1f}/{car.get('fuelCapacity', 0):.1f}L ({car.get('fuelRemainingLaps', 0):.1f} laps) | Mix: {fuel_mix}")
            start_y += 1
            
            # ERS stats
            ers_pct = car.get('ersStoreEnergy', 0) / MAX_ERS_ENERGY * 100
            ers_deploy_mode = ERS_DEPLOYMENT_MODES.get(car.get('ersDeployMode', 0), "Unknown")
            ers_color = curses.color_pair(1) if ers_pct > 50 else curses.color_pair(2) if ers_pct > 20 else curses.color_pair(3)
            ers_mgu_k = car.get('ersHarvestedThisLapMGUK', 0) / 1000
            ers_mgu_h = car.get('ersHarvestedThisLapMGUH', 0) / 1000
            ers_deployed = car.get('ersDeployedThisLap', 0) / 1000
            
            self.stdscr.addstr(start_y, 0, f"ERS: {ers_pct:.1f}% | Mode: {ers_deploy_mode}", ers_color)
            start_y += 1
            self.stdscr.addstr(start_y, 0, 
                f"Harvest - MGU-K: {ers_mgu_k:.1f}kJ | MGU-H: {ers_mgu_h:.1f}kJ | Deploy: {ers_deployed:.1f}kJ")
            start_y += 1
            
            # Tire info
            compound = TYRE_COMPOUNDS.get(car.get('actualTyreCompound', 0), "Unknown")
            age = car.get('tyresAgeLaps', 0)
            self.stdscr.addstr(start_y, 0, f"Tires: {compound} (Age: {age} laps)")
            start_y += 1
            
            # DRS and Flags
            drs_status = "Available" if car.get('drsAllowed', 0) == 1 else "Not Available"
            drs_distance = car.get('drsActivationDistance', 0)
            flag = FLAG_COLORS.get(car.get('vehicleFiaFlags', -1), "None")
            
            flag_color = curses.color_pair(1) if flag == "Green" else curses.color_pair(2) if flag == "Yellow" else curses.color_pair(3) if flag == "Red" else curses.color_pair(0)
            self.stdscr.addstr(start_y, 0, f"DRS: {drs_status}")
            if drs_distance > 0:
                self.stdscr.addstr(f" ({drs_distance}m)")
            self.stdscr.addstr(" | Flag: ")
            self.stdscr.addstr(flag, flag_color)
            start_y += 2
            
        return start_y

    def display_car_setup(self, start_y: int) -> int:
        """Display car setup data"""
        self.stdscr.addstr(start_y, 0, "=== CAR SETUP (Player) ===", curses.A_BOLD | curses.color_pair(5))
        start_y += 1
        
        if "carSetups" in self.data["car_setups"]:
            car_index = min(self.player_car_index, len(self.data["car_setups"]["carSetups"]) - 1)
            setup = self.data["car_setups"]["carSetups"][car_index]  # Player's car            # Aero
            self.stdscr.addstr(start_y, 0, f"Wings (F/R): {setup.get('frontWing', 0)}/{setup.get('rearWing', 0)}")
            start_y += 1
            
            # Suspension
            self.stdscr.addstr(start_y, 0, 
                f"Suspension (F/R): {setup.get('frontSuspension', 0)}/{setup.get('rearSuspension', 0)} | "
                f"Height: {setup.get('frontSuspensionHeight', 0)}/{setup.get('rearSuspensionHeight', 0)}")
            start_y += 1
            
            # Tyre pressures (FL, FR, RL, RR)
            tyre_pressures = setup.get('tyrePressure', [0, 0, 0, 0])
            self.stdscr.addstr(start_y, 0, 
                f"Tyre Pressures - FL: {tyre_pressures[2]:.1f} FR: {tyre_pressures[3]:.1f} "
                f"RL: {tyre_pressures[0]:.1f} RR: {tyre_pressures[1]:.1f}")
            start_y += 1
            
            # Brake bias
            self.stdscr.addstr(start_y, 0, f"Brake Bias: {setup.get('brakeBias', 0)}% | Brake Pressure: {setup.get('brakePressure', 0)}%")
            start_y += 2
            
        return start_y

    def display_session(self, start_y: int) -> int:
        """Display session data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== SESSION INFO ===", header_attr)
        start_y += 1
        
        if session := self.data["session"]:
            track_temp = session.get("trackTemperature", 0)
            air_temp = session.get("airTemperature", 0)
            weather = session.get("weather", 0)
            track_length = session.get("trackLength", 0)
            session_type = session.get("sessionType", 0)
            session_duration = session.get("sessionDuration", 0)  # In minutes
            total_laps = session.get("totalLaps", 0)
            pit_speed = session.get("pitSpeedLimit", 0)
            
            # Parse marshal zones for safety car status
            marshal_zones = session.get("marshalZones", [])
            safety_car = 0  # Default to no safety car
            if marshal_zones:
                # Check if any marshal zone has a yellow (-1) or red (-2) flag
                for zone in marshal_zones:
                    if zone.get("m_zoneFlag", 0) in [-1, -2]:
                        safety_car = 1  # Assume safety car if there are yellow/red flags
            
            session_str = SESSION_TYPES.get(session_type, "Unknown")
            weather_str = WEATHER_TYPES.get(weather, "Unknown")
            safety_car_str = "None" if safety_car == 0 else "SC"
            
            # Get time remaining from duration in minutes
            minutes = session_duration
            seconds = 0
            
            # Get weather forecast if available
            forecast = session.get("weatherForecast", [])
            
            # Session info
            self.stdscr.addstr(start_y, 0, f"Session: {session_str} | Duration: {minutes:02d}m")
            start_y += 1

            # Track conditions
            weather_color = (curses.color_pair(1) if weather == 0 else  # Clear
                           curses.color_pair(2) if weather in [1, 2] else  # Light Cloud/Overcast
                           curses.color_pair(3))  # Rain/Storm
            
            self.stdscr.addstr(start_y, 0, f"Track: {track_temp}°C | Air: {air_temp}°C | Weather: ")
            self.stdscr.addstr(weather_str, weather_color)
            start_y += 1

            # Track info and safety
            self.stdscr.addstr(start_y, 0, f"Track Length: {track_length}m | Laps: {total_laps} | Pit Limit: {pit_speed}km/h")
            start_y += 1

            # Show upcoming weather if available
            if forecast and len(forecast) > 0:
                next_weather = forecast[0]
                if next_weather["weather"] != weather:  # Only show if weather will change
                    change_str = WEATHER_TYPES.get(next_weather["weather"], "Unknown")
                    time_offset = next_weather["timeOffset"]
                    self.stdscr.addstr(start_y, 0, f"Weather Change: {change_str} in {time_offset}m")
                    start_y += 1

            start_y += 1
            
        return start_y

    def display_motion(self, start_y: int) -> int:
        """Display motion data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== MOTION DATA ===", header_attr)
        start_y += 1
        
        if motion := self.data["motion"]:
            if "cars" in motion and motion["cars"] and "playerExtra" in motion:
                # Make sure we don't try to access an index beyond what's available
                car_index = min(self.player_car_index, len(motion["cars"]) - 1)
                car = motion["cars"][car_index]  # Player's car
                extra = motion["playerExtra"]
                
                # Position and velocity
                pos = car.get("worldPosition", [0, 0, 0])
                vel = car.get("worldVelocity", [0, 0, 0])
                vel_mag = (vel[0]**2 + vel[1]**2 + vel[2]**2)**0.5  # Velocity magnitude
                
                # Acceleration
                gforce = car.get("gForces", [0, 0, 0])
                lat_g = gforce[0]
                lon_g = gforce[1]
                vert_g = gforce[2]
                
                # Roll, pitch, yaw
                rotation = car.get("rotation", [0, 0, 0])
                yaw = rotation[0]
                pitch = rotation[1]
                roll = rotation[2]
                
                # Suspension
                susp = extra.get("suspensionPosition", [0, 0, 0, 0])
                susp_vel = extra.get("suspensionVelocity", [0, 0, 0, 0])
                susp_acc = extra.get("suspensionAcceleration", [0, 0, 0, 0])
                
                # Display position and velocity
                self.stdscr.addstr(start_y, 0, f"Pos: X:{pos[0]:7.1f} Y:{pos[1]:7.1f} Z:{pos[2]:7.1f} | Speed: {vel_mag*3.6:6.1f} km/h")
                start_y += 1
                
                # G-Forces with color coding
                g_color = lambda g: curses.color_pair(1) if abs(g) < 2 else curses.color_pair(2) if abs(g) < 4 else curses.color_pair(3)
                self.stdscr.addstr(start_y, 0, "G-Force - ")
                self.stdscr.addstr(f"Lat: {lat_g:5.2f}g ", g_color(lat_g))
                self.stdscr.addstr("| ")
                self.stdscr.addstr(f"Lon: {lon_g:5.2f}g ", g_color(lon_g))
                self.stdscr.addstr("| ")
                self.stdscr.addstr(f"Vert: {vert_g:5.2f}g", g_color(vert_g))
                start_y += 1
                
                # Attitude
                self.stdscr.addstr(start_y, 0, f"Attitude - Roll: {roll:6.2f}° | Pitch: {pitch:6.2f}° | Yaw: {yaw:6.2f}°")
                start_y += 1
                
                # Suspension
                self.stdscr.addstr(start_y, 0, "Suspension Pos - ")
                for i, pos in enumerate(susp):
                    corner = ["RL", "RR", "FL", "FR"][i]
                    self.stdscr.addstr(f"{corner}: {pos:6.3f}m ")
                start_y += 1
                
                self.stdscr.addstr(start_y, 0, "Suspension Vel - ")
                for i, vel in enumerate(susp_vel):
                    corner = ["RL", "RR", "FL", "FR"][i]
                    self.stdscr.addstr(f"{corner}: {vel:6.3f}m/s ")
                start_y += 2
                
        return start_y

    def display_lap_data(self, start_y: int) -> int:
        """Display lap data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== LAP DATA ===", header_attr)
        start_y += 1
        
        if lap_data := self.data["lap_data"]:
            if "laps" in lap_data and lap_data["laps"]:
                car_index = min(self.player_car_index, len(lap_data["laps"]) - 1)
                player_data = lap_data["laps"][car_index]  # Player's car
                
                # Format times properly
                last_lap_ms = player_data.get("lastLapTimeInMS", 0)
                last_lap_time = f"{last_lap_ms/1000:.3f}" if last_lap_ms > 0 else "N/A"
                
                s1_ms = player_data.get("sector1TimeInMS", 0)
                s2_ms = player_data.get("sector2TimeInMS", 0)
                s3_ms = player_data.get("sector3TimeInMS", 0)
                
                s1_time = f"{s1_ms/1000:.3f}" if s1_ms > 0 else "N/A"
                s2_time = f"{s2_ms/1000:.3f}" if s2_ms > 0 else "N/A"
                s3_time = f"{s3_ms/1000:.3f}" if s3_ms > 0 else "N/A"
                
                # Display position and current lap
                pos = player_data.get("carPosition", 0)
                current_lap = player_data.get("currentLapNum", 0)
                driver_status = DRIVER_STATUS.get(player_data.get("driverStatus", 0), "Unknown")
                result_status = RESULT_STATUS.get(player_data.get("resultStatus", 0), "Unknown")
                
                self.stdscr.addstr(start_y, 0, f"Position: P{pos} | Lap: {current_lap} | Status: {driver_status}")
                start_y += 1
                self.stdscr.addstr(start_y, 0, f"Last Lap: {last_lap_time}")
                start_y += 1
                self.stdscr.addstr(start_y, 0, f"Sectors: {s1_time} | {s2_time} | {s3_time}")
                start_y += 2
            
        return start_y

    def display_car_telemetry(self, start_y: int) -> int:
        """Display car telemetry data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== TELEMETRY ===", header_attr)
        start_y += 1
        
        if telemetry := self.data["car_telemetry"]:
            if "carTelemetry" in telemetry and telemetry["carTelemetry"]:
                car_index = min(self.player_car_index, len(telemetry["carTelemetry"]) - 1)
                car = telemetry["carTelemetry"][car_index]  # Player's car
                
                # Basic telemetry
                speed = int(car.get("speedKph", 0))
                gear = car.get("gear", 0)
                gear_str = "R" if gear == -1 else "N" if gear == 0 else str(gear)
                rpm = car.get("engineRPM", 0)
                throttle = float(car.get("throttle", 0)) * 100
                brake = float(car.get("brake", 0)) * 100
                drs = "ACTIVE" if car.get("drs", 0) == 1 else "OFF"
                rev_lights = car.get("revLightsPercent", 0)
                
                # Highlight DRS and RPMs
                drs_color = curses.color_pair(1) if drs == "ACTIVE" else curses.color_pair(0)
                rpm_color = curses.color_pair(1) if rev_lights < 80 else curses.color_pair(2) if rev_lights < 90 else curses.color_pair(3)
                
                # Speed and basic controls
                self.stdscr.addstr(start_y, 0, f"Speed: {speed:3d}km/h | Gear: {gear_str:>2} | ")
                self.stdscr.addstr(f"RPM: {rpm:5d}", rpm_color)
                start_y += 1
                
                self.stdscr.addstr(start_y, 0, f"Throttle: {throttle:3.0f}% | Brake: {brake:3.0f}% | ")
                self.stdscr.addstr(f"DRS: {drs}", drs_color)
                start_y += 1
                
                # Temperatures
                tyre_temps = car.get("tyresSurfaceTemperature", [0, 0, 0, 0])
                tyre_inner_temps = car.get("tyresInnerTemperature", [0, 0, 0, 0])
                brake_temps = car.get("brakesTemperature", [0, 0, 0, 0])
                
                self.stdscr.addstr(start_y, 0, 
                    f"Tyre Surface - FL: {tyre_temps[2]:3d}°C FR: {tyre_temps[3]:3d}°C RL: {tyre_temps[0]:3d}°C RR: {tyre_temps[1]:3d}°C")
                start_y += 1
                
                self.stdscr.addstr(start_y, 0,
                    f"Tyre Core   - FL: {tyre_inner_temps[2]:3d}°C FR: {tyre_inner_temps[3]:3d}°C RL: {tyre_inner_temps[0]:3d}°C RR: {tyre_inner_temps[1]:3d}°C")
                start_y += 1
                
                self.stdscr.addstr(start_y, 0,
                    f"Brakes      - FL: {brake_temps[2]:3d}°C FR: {brake_temps[3]:3d}°C RL: {brake_temps[0]:3d}°C RR: {brake_temps[1]:3d}°C")
                start_y += 2
                
            return start_y
                
    def display_event(self, start_y: int) -> int:
        """Display event data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== EVENTS ===", header_attr)
        start_y += 1
        
        if event := self.data["event"]:
            # Common events
            events = {
                "SSTA": "Session Started",
                "SEND": "Session Ended",
                "FTLP": "Fastest Lap",
                "RTMT": "Retirement",
                "DRSE": "DRS Enabled",
                "DRSD": "DRS Disabled",
                "TMPT": "Team Mate Pitting",
                "CHQF": "Chequered Flag",
                "RCWN": "Race Winner",
                "PENA": "Penalty Issued",
                "SPTP": "Speed Trap Triggered",
                "STLG": "Start Lights",
                "LGOT": "Lights Out",
                "DTSV": "Drive Through Served",
                "SGSV": "Stop Go Served",
                "FLBK": "Flashback",
                "BUTN": "Button Status Changed",
            }
            
            # Display recent events
            self.stdscr.addstr(start_y, 0, "Recent Events:", curses.A_BOLD)
            start_y += 1
            
            if "eventHistory" in event:
                for event_entry in event["eventHistory"]:
                    event_code = event_entry["code"]
                    if not event_code or event_code == "NULL":
                        continue
                        
                    event_name = events.get(event_code, event_code)
                    event_time = event_entry["time"]
                    details = event_entry["details"]
                    
                    # Format details based on event type
                    detail_str = ""
                    if event_code == "FTLP":  # Fastest Lap
                        if "vehicleIdx" in details and "lapTime" in details:
                            detail_str = f" - Car {details['vehicleIdx']} ({details['lapTime']:.3f}s)"
                    elif event_code == "SPTP":  # Speed Trap
                        if "vehicleIdx" in details and "speedKph" in details:  # Note: changed from speed to speedKph
                            detail_str = f" - Car {details['vehicleIdx']} ({details['speedKph']:.1f} km/h)"
                    elif event_code == "PENA":  # Penalty
                        if "vehicleIdx" in details and "penaltyType" in details:
                            detail_str = f" - Car {details['vehicleIdx']} (Lap {details.get('lapNum', 0)})"
                    elif event_code == "STLG":  # Start Lights
                        if "numLights" in details:
                            detail_str = f" - {details['numLights']} lights"
                    elif "vehicleIdx" in details:
                        detail_str = f" - Car {details['vehicleIdx']}"
                    
                    color = curses.color_pair(1)  # Default color
                    
                    # Color code specific events
                    if event_code in ["PENA"]:  # Penalties in yellow
                        color = curses.color_pair(2)
                    elif event_code in ["FTLP", "RCWN"]:  # Positive events in green
                        color = curses.color_pair(1)
                    elif event_code in ["RTMT"]:  # Negative events in red
                        color = curses.color_pair(3)
                    
                    self.stdscr.addstr(start_y, 0, f"[{event_time}] {event_name}{detail_str}", color)
                    start_y += 1
            else:
                self.stdscr.addstr(start_y, 0, "No events yet", curses.color_pair(2))
                start_y += 1
            
            start_y += 1
            
        return start_y

    def display_car_damage(self, start_y: int) -> int:
        """Display car damage data"""
        header_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(start_y, 0, "=== DAMAGE ===", header_attr)
        start_y += 1
        
        if damage := self.data["car_damage"]:
            if "carDamage" in damage and damage["carDamage"]:
                car_index = min(self.player_car_index, len(damage["carDamage"]) - 1)
                car = damage["carDamage"][car_index]  # Player's car
                
                # Tyre wear
                if "m_tyresWear" in car:
                    wear = car["m_tyresWear"]
                    damage = car.get("m_tyresDamage", [0, 0, 0, 0])
                    for i, (w, d) in enumerate(zip(wear, damage)):
                        color = curses.color_pair(1) if w < 20 else curses.color_pair(2) if w < 50 else curses.color_pair(3)
                        pos = ["RL", "RR", "FL", "FR"][i]
                        self.stdscr.addstr(start_y, i*20, f"{pos}: {w:3.0f}% ({d}%)", color)
                    start_y += 1
                
                # Wing damage
                front_left = car.get("m_frontLeftWingDamage", 0)
                front_right = car.get("m_frontRightWingDamage", 0)
                rear = car.get("m_rearWingDamage", 0)
                floor = car.get("m_floorDamage", 0)
                diffuser = car.get("m_diffuserDamage", 0)
                
                wing_color = curses.color_pair(1) if max(front_left, front_right, rear) < 20 else curses.color_pair(2) if max(front_left, front_right, rear) < 50 else curses.color_pair(3)
                self.stdscr.addstr(start_y, 0, f"Wings - Front L/R: {front_left}%/{front_right}% | Rear: {rear}%", wing_color)
                start_y += 1
                self.stdscr.addstr(start_y, 0, f"Aero - Floor: {floor}% | Diffuser: {diffuser}%")
                start_y += 2
            
        return start_y

    def display(self):
        """Update the display with current telemetry data"""
        self.stdscr.clear()
        
        # Display title and timestamp
        title_attr = curses.A_BOLD | curses.color_pair(5)
        self.stdscr.addstr(0, 0, "=== F1 22 LIVE TELEMETRY ===", title_attr)
        self.stdscr.addstr(1, 0, "Press 'q' to quit", curses.color_pair(2))
        current_y = 3
        
        try:
            # Display sections in sequence
            
            current_y = self.display_session(current_y)
            current_y = self.display_motion(current_y)
            current_y = self.display_lap_data(current_y)
            current_y = self.display_car_telemetry(current_y)
            current_y = self.display_car_status(current_y)
            current_y = self.display_car_damage(current_y)
            current_y = self.display_car_setup(current_y)
            current_y = self.display_participants(current_y)
            current_y = self.display_event(current_y)            # Display packet statistics at the bottom
            max_y, max_x = self.stdscr.getmaxyx()
            stats_y = max_y - 3  # Leave more room for stats
            if stats_y > current_y:
                # Show packet type counters with unique abbreviations
                packet_abbrevs = {
                    "motion": "MOT",
                    "session": "SES",
                    "lap_data": "LAP",
                    "event": "EVT",
                    "participants": "PRT",
                    "car_setups": "SET",
                    "car_telemetry": "TEL",
                    "car_status": "STA",
                    "final_classification": "FIN",
                    "lobby_info": "LOB",
                    "car_damage": "DMG",
                    "session_history": "HST"
                }
                stats_str = " | ".join([f"{packet_abbrevs[k]}: {v}" for k, v in self.packet_counts.items()])
                
                # Split into two lines if needed
                if len(stats_str) > max_x:
                    half = len(self.packet_counts) // 2
                    counts1 = dict(list(self.packet_counts.items())[:half])
                    counts2 = dict(list(self.packet_counts.items())[half:])
                    
                    stats_str1 = " | ".join([f"{packet_abbrevs[k]}: {v}" for k, v in counts1.items()])
                    stats_str2 = " | ".join([f"{packet_abbrevs[k]}: {v}" for k, v in counts2.items()])
                    
                    self.stdscr.addstr(stats_y, 0, stats_str1, curses.color_pair(5))
                    self.stdscr.addstr(stats_y + 1, 0, stats_str2, curses.color_pair(5))
                else:
                    self.stdscr.addstr(stats_y, 0, stats_str, curses.color_pair(5))
        except curses.error:
            # Handle case where terminal is too small
            pass
        
        # Update the screen
        self.stdscr.refresh()

def run_telemetry(stdscr, bind_ip: str, port: int):
    """Main telemetry display loop"""
    
    # Initialize display
    display = TelemetryDisplay(stdscr)
    
    # Set up UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, port))
    sock.settimeout(0.1)  # Non-blocking socket
    
    # Initialize timer for display updates
    last_update = time.time()
    UPDATE_INTERVAL = 0.016667  # 60 Hz refresh rate
    
    while True:
        try:
            # Check for quit command
            c = stdscr.getch()
            if c == ord('q'):
                break
                
            # Process all available UDP packets
            packets_processed = 0
            while packets_processed < 100:  # Limit to prevent infinite loop
                try:
                    data, addr = sock.recvfrom(2048)
                    buf = memoryview(data)
                    
                    # Parse header
                    hdr = PacketHeader.from_buf(buf)
                    pid = hdr.m_packetId
                    
                    # Process packet if it's one we're interested in
                    if pid in PACKET_TYPES:
                        packet_name, decoder = PACKET_TYPES[pid]
                        payload = decoder(buf)
                        display.update_data(packet_name, payload, hdr)
                    
                    packets_processed += 1
                except socket.timeout:
                    break  # No more packets waiting
                
            # Update display at fixed interval
            current_time = time.time()
            if current_time - last_update >= UPDATE_INTERVAL:
                display.display()
                last_update = current_time
            
        except KeyboardInterrupt:
            break
            
    # Clean up
    sock.close()

def main():
    # Parse command line arguments
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=20777)
    args = ap.parse_args()
    
    # Run the telemetry display
    curses.wrapper(run_telemetry, args.ip, args.port)

if __name__ == "__main__":
    main()