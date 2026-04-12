import curses
import json
import socket
import sys
import struct
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import packet parsers
from src.udp_parser import (
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
    decode_tyre_sets,
    decode_motion_ex,
    decode_time_trial,
    decode_lap_positions,
    PACKET_ID,
)

# Import constants
from src.udp_parser.constants import (
    WEATHER_TYPES,
    SESSION_TYPES,
    SURFACE_TYPES,
    TYRE_COMPOUNDS,
    ERS_DEPLOYMENT_MODES,
    FLAG_COLORS,
    RESULT_STATUS,
    DRIVER_STATUS,
    MAX_ERS_ENERGY,
    TEAM_NAMES,
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
    12: ("tyre_sets", decode_tyre_sets),
    13: ("motion_ex", decode_motion_ex),
    14: ("time_trial", decode_time_trial),
    15: ("lap_positions", decode_lap_positions),
}




class TelemetryDisplay:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.player_car_index = 0
        self.packet_counts = {key: 0 for key in ["motion", "motion_ex", "tyre_sets", "time_trial", "lap_positions",
                                               "session", "lap_data", "event", "participants", 
                                               "car_setups", "car_telemetry", "car_status", "final_classification", 
                                               "lobby_info", "car_damage", "session_history"]}
        # Simplified data structure for compact display
        self.data = {
            "session": {"trackName": "Unknown", "sessionTypeName": "Unknown", "weatherName": "Clear", 
                       "trackTemperature": 0, "airTemperature": 0, "sessionTimeLeftFormatted": "00:00"},
            "lap_data": {"laps": [{"carPosition": 0, "currentLapNum": 0, "lastLapTimeFormatted": "0:00.000", 
                                 "sector1TimeFormatted": "00.000", "sector2TimeFormatted": "00.000", 
                                 "driverStatusName": "Unknown", "resultStatusName": "Unknown"}]},
            "car_telemetry": {"carTelemetry": [{"speedKph": 0, "speedMph": 0, "gearDisplay": "N", "engineRPM": 0, 
                                              "throttlePercent": 0, "brakePercent": 0, "drsStatus": "Off", 
                                              "tyresSurfaceTemperature": [0,0,0,0], "brakesTemperature": [0,0,0,0],
                                              "engineTemperature": 0, "engineTempStatus": "OK", "hasEngineWarning": False,
                                              "hasBrakeWarning": False, "hasTyreWarning": False}]},
            "car_status": {"carStatus": [{"fuelPercentage": 0, "fuelRemainingLaps": 0, "fuelMixName": "Standard",
                                        "ersPercentage": 0, "ersDeployModeName": "None", "actualTyreCompoundName": "Unknown",
                                        "tyresAgeLaps": 0, "drsStatus": "Not allowed", "flagColor": "None"}]},
            "car_damage": {"carDamage": [{"m_tyresWear": [0,0,0,0], "m_frontLeftWingDamage": 0, "m_frontRightWingDamage": 0,
                                        "m_rearWingDamage": 0, "m_floorDamage": 0}]},
            "motion_ex": {"playerExtra": {}},
            "tyre_sets": {"latest": None},
            "time_trial": {
                "playerSessionBestDataSet": None,
                "personalBestDataSet": None,
                "rivalDataSet": None,
            },
            "lap_positions": {"positions": [], "numLaps": 0, "lapStart": 0},
            "participants": {"participants": []},
            "event": {"eventHistory": []}
        }
        # Initialize curses
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)    # Good
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # Warning
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)      # Critical
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)     # Headers
        curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)     # Info
        self.stdscr.nodelay(1)

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
        
    def display_race_standings(self, start_y: int) -> int:
        """Display comprehensive race standings with all drivers"""
        # Session header (2 lines)
        session = self.data["session"]
        self.stdscr.addstr(start_y, 0, f"=== F1 RACE MONITOR === {session.get('trackName', 'Unknown')} | {session.get('sessionTypeName', 'Unknown')} | {session.get('weatherName', 'Clear')}", curses.A_BOLD | curses.color_pair(4))
        start_y += 1
        self.stdscr.addstr(start_y, 0, f"Track: {session.get('trackTemperature', 0)}°C | Air: {session.get('airTemperature', 0)}°C | Time: {session.get('sessionTimeLeftFormatted', '00:00')}")
        start_y += 2
        
        # Race standings header
        self.stdscr.addstr(start_y, 0, "=== RACE STANDINGS ===", curses.A_BOLD | curses.color_pair(5))
        start_y += 1
        self.stdscr.addstr(start_y, 0, "Pos Driver           Team           Lap  Last Lap    S1     S2     Status", curses.A_BOLD)
        start_y += 1
        
        # Combine participants and lap data for comprehensive view
        if self.data["participants"]["participants"] and self.data["lap_data"]["laps"]:
            # Create combined driver data
            drivers_data = []
            participants = self.data["participants"]["participants"]
            lap_data = self.data["lap_data"]["laps"]
            
            for i in range(min(len(participants), len(lap_data), 22)):
                participant = participants[i]
                lap = lap_data[i]
                
                if participant.get("displayName") or participant.get("name"):  # Only show active drivers
                    driver_name = participant.get("displayName", participant.get("name", "Unknown"))[:12]
                    team_name = participant.get("teamName", "Unknown")[:12]
                    position = lap.get("carPosition", 0)
                    current_lap = lap.get("currentLapNum", 0)
                    last_lap = lap.get("lastLapTimeFormatted", "0:00.000")
                    s1_time = lap.get("sector1TimeFormatted", "00.000")
                    s2_time = lap.get("sector2TimeFormatted", "00.000")
                    status = lap.get("driverStatusName", "Unknown")[:8]
                    
                    drivers_data.append({
                        "position": position,
                        "name": driver_name,
                        "team": team_name,
                        "lap": current_lap,
                        "last_lap": last_lap,
                        "s1": s1_time,
                        "s2": s2_time,
                        "status": status,
                        "car_index": i
                    })
            
            # Sort by position
            drivers_data.sort(key=lambda x: x["position"] if x["position"] > 0 else 999)
            
            # Display drivers (limit to available screen space)
            max_y, _ = self.stdscr.getmaxyx()
            max_drivers = min(len(drivers_data), max_y - start_y - 15)  # Leave space for player info
            
            for i, driver in enumerate(drivers_data[:max_drivers]):
                if driver["position"] > 0:  # Only show drivers with valid positions
                    # Color coding for positions
                    pos_color = (curses.color_pair(1) if driver["position"] <= 3 else 
                               curses.color_pair(2) if driver["position"] <= 10 else 
                               curses.color_pair(0))
                    
                    # Highlight player's car
                    if driver["car_index"] == self.player_car_index:
                        pos_color |= curses.A_REVERSE
                    
                    # Format the line
                    line = f"{driver['position']:2d}  {driver['name']:<12} {driver['team']:<12} {driver['lap']:3d}  {driver['last_lap']:<8} {driver['s1']:<6} {driver['s2']:<6} {driver['status']}"
                    self.stdscr.addstr(start_y, 0, line[:78], pos_color)  # Truncate to fit screen
                    start_y += 1
        
        start_y += 1
        return start_y
    
    def display_player_details(self, start_y: int) -> int:
        """Display detailed player car information"""
        # Player telemetry (compact)
        if self.data["car_telemetry"]["carTelemetry"]:
            tel = self.data["car_telemetry"]["carTelemetry"][min(self.player_car_index, len(self.data["car_telemetry"]["carTelemetry"])-1)]
            self.stdscr.addstr(start_y, 0, "=== PLAYER CAR ===", curses.A_BOLD | curses.color_pair(5))
            start_y += 1
            
            # Speed and controls
            rpm_color = curses.color_pair(1) if tel.get("engineRPM", 0) < 10000 else curses.color_pair(2) if tel.get("engineRPM", 0) < 12000 else curses.color_pair(3)
            drs_color = curses.color_pair(1) if tel.get("drsStatus", "Off") != "Off" else curses.color_pair(0)
            
            self.stdscr.addstr(start_y, 0, f"Speed: {tel.get('speedKph', 0):3d}km/h | Gear: {tel.get('gearDisplay', 'N'):>2} | ")
            self.stdscr.addstr(f"RPM: {tel.get('engineRPM', 0):5d}", rpm_color)
            self.stdscr.addstr(f" | DRS: ")
            self.stdscr.addstr(tel.get('drsStatus', 'Off'), drs_color)
            start_y += 1
            
            # Inputs and temperatures
            self.stdscr.addstr(start_y, 0, f"Throttle: {tel.get('throttlePercent', 0):3.0f}% | Brake: {tel.get('brakePercent', 0):3.0f}% | Engine: {tel.get('engineTemperature', 0):3d}°C")
            start_y += 1
        
        # Car status
        if self.data["car_status"]["carStatus"]:
            status = self.data["car_status"]["carStatus"][min(self.player_car_index, len(self.data["car_status"]["carStatus"])-1)]
            
            # Fuel and ERS
            fuel_pct = status.get("fuelPercentage", 0)
            fuel_color = curses.color_pair(1) if fuel_pct > 25 else curses.color_pair(2) if fuel_pct > 10 else curses.color_pair(3)
            ers_pct = status.get("ersPercentage", 0)
            ers_color = curses.color_pair(1) if ers_pct > 50 else curses.color_pair(2) if ers_pct > 20 else curses.color_pair(3)
            
            self.stdscr.addstr(start_y, 0, f"Fuel: ")
            self.stdscr.addstr(f"{fuel_pct:.1f}%", fuel_color)
            self.stdscr.addstr(f" ({status.get('fuelRemainingLaps', 0):.1f} laps) | ERS: ")
            self.stdscr.addstr(f"{ers_pct:.0f}%", ers_color)
            self.stdscr.addstr(f" | Tyres: {status.get('actualTyreCompoundName', 'Unknown')} ({status.get('tyresAgeLaps', 0)} laps)")
            start_y += 1
        
        # Damage summary
        if self.data["car_damage"]["carDamage"]:
            damage = self.data["car_damage"]["carDamage"][min(self.player_car_index, len(self.data["car_damage"]["carDamage"])-1)]
            wear = damage.get("m_tyresWear", [0,0,0,0])
            max_wear = max(wear) if wear else 0
            wing_dmg = max(damage.get("m_frontLeftWingDamage", 0), damage.get("m_frontRightWingDamage", 0), damage.get("m_rearWingDamage", 0))
            
            wear_color = curses.color_pair(1) if max_wear < 30 else curses.color_pair(2) if max_wear < 70 else curses.color_pair(3)
            wing_color = curses.color_pair(1) if wing_dmg < 20 else curses.color_pair(2) if wing_dmg < 50 else curses.color_pair(3)
            
            self.stdscr.addstr(start_y, 0, f"Tyre Wear: ")
            self.stdscr.addstr(f"Max {max_wear:.0f}%", wear_color)
            self.stdscr.addstr(f" | Wing Damage: ")
            self.stdscr.addstr(f"Max {wing_dmg}%", wing_color)
            start_y += 1
        
        start_y += 1
        return start_y
    
    def display_recent_events(self, start_y: int) -> int:
        """Display recent race events"""
        self.stdscr.addstr(start_y, 0, "=== RECENT EVENTS ===", curses.A_BOLD | curses.color_pair(5))
        start_y += 1
        
        if self.data["event"]["eventHistory"]:
            for i, event in enumerate(self.data["event"]["eventHistory"][:3]):  # Show max 3 events
                if event.get("code") and event["code"] != "NULL":
                    event_name = event.get("eventName", event["code"])
                    event_time = event.get("time", "")
                    color = curses.color_pair(2) if "PENA" in event["code"] else curses.color_pair(1) if "FTLP" in event["code"] else curses.color_pair(0)
                    self.stdscr.addstr(start_y, 0, f"[{event_time}] {event_name}"[:78], color)
                    start_y += 1
        else:
            self.stdscr.addstr(start_y, 0, "No events yet", curses.color_pair(2))
            start_y += 1
        
        return start_y

    def display(self):
        """Update the display with comprehensive race information"""
        self.stdscr.clear()
        
        try:
            # Title (1 line)
            self.stdscr.addstr(0, 0, "F1 25 RACE MONITOR - Press 'q' to quit", curses.A_BOLD | curses.color_pair(4))
            
            # Race standings and comprehensive info
            current_y = self.display_race_standings(2)
            current_y = self.display_player_details(current_y)
            current_y = self.display_recent_events(current_y)
            
            # Packet statistics at bottom (2 lines max)
            max_y, max_x = self.stdscr.getmaxyx()
            if max_y > current_y + 3:
                stats_y = max_y - 2
                packet_abbrevs = {
                    "motion": "MOT",
                    "motion_ex": "MEX",
                    "tyre_sets": "TYR",
                    "time_trial": "TT",
                    "lap_positions": "LPS",
                    "session": "SES",
                    "lap_data": "LAP",
                    "event": "EVT",
                    "participants": "PRT",
                    "car_setups": "SET",
                    "car_telemetry": "TEL",
                    "car_status": "STA",
                    "car_damage": "DMG"
                }
                
                # Split stats into two lines
                items = list(self.packet_counts.items())
                mid = len(items) // 2
                
                stats1 = " | ".join([f"{packet_abbrevs.get(k, k[:3].upper())}: {v}" for k, v in items[:mid]])
                stats2 = " | ".join([f"{packet_abbrevs.get(k, k[:3].upper())}: {v}" for k, v in items[mid:]])
                
                self.stdscr.addstr(stats_y, 0, stats1[:max_x-1], curses.color_pair(5))
                self.stdscr.addstr(stats_y + 1, 0, stats2[:max_x-1], curses.color_pair(5))
                
        except curses.error:
            # Handle terminal too small
            self.stdscr.addstr(0, 0, "Terminal too small - resize window", curses.color_pair(3))
        
        self.stdscr.refresh()

def run_telemetry(stdscr, bind_ip: str, port: int):
    """Main telemetry display loop"""
    
    # Initialize display
    display = TelemetryDisplay(stdscr)
    
    # Set up UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, port))
    sock.settimeout(0.01)  # Very short timeout for responsive display (10ms)
    
    # Initialize timer for display updates
    last_update = time.time()
    UPDATE_INTERVAL = 0.033333  # 30 Hz refresh rate (good balance of smoothness and performance)
    
    while True:
        try:
            # Check for quit command
            c = stdscr.getch()
            if c == ord('q'):
                break
                
            # Process all available UDP packets (non-blocking)
            packets_processed = 0
            packet_received = False
            
            while packets_processed < 50:  # Process up to 50 packets per loop
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
                        packet_received = True
                    
                    packets_processed += 1
                except socket.timeout:
                    break  # No more packets waiting
                
            # Update display at fixed interval OR when new data arrives
            current_time = time.time()
            if (current_time - last_update >= UPDATE_INTERVAL) or packet_received:
                display.display()
                last_update = current_time
                
            # Small sleep to prevent excessive CPU usage when no packets
            if not packet_received:
                time.sleep(0.005)  # 5ms sleep when idle
            
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
