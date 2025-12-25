#!/usr/bin/env python3
"""
F1 Telemetry HTTP MCP Server

An HTTP/SSE MCP server that provides live F1 22 telemetry data for OpenAI API integration.
This server exposes F1 telemetry through HTTP endpoints compatible with OpenAI's MCP tool.
"""

import json
import socket
import threading
import time
from typing import Dict, Any, Optional, List
import logging
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import uuid

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
        
        # Telemetry data storage
        self.data = {
            "session": {},
            "lap_data": {"laps": []},
            "car_telemetry": {"carTelemetry": []},
            "car_status": {"carStatus": []},
            "car_damage": {"carDamage": []},
            "participants": {"participants": []},
            "motion": {"cars": [], "playerExtra": {}},
            "event": {"eventHistory": []},
            "car_setups": {"carSetups": []},
            "lobby_info": {"lobbyPlayers": []},
            "final_classification": None,
            "session_history": None
        }
        
        self.player_car_index = 0
        self.last_update = time.time()
        
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
                    
                    # Update player car index
                    if hasattr(hdr, 'm_playerCarIndex'):
                        self.player_car_index = hdr.m_playerCarIndex
                    
                    # Process packet if it's one we're interested in
                    if pid in PACKET_TYPES:
                        packet_name, decoder = PACKET_TYPES[pid]
                        payload = decoder(buf)
                        self._update_data(packet_name, payload)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error processing packet: {e}")
                    
        except Exception as e:
            logger.error(f"Error in capture loop: {e}")
        finally:
            if self.sock:
                self.sock.close()
                
    def _update_data(self, packet_type: str, data: Dict[str, Any]):
        """Update stored telemetry data"""
        if packet_type == "event":
            # Handle events specially - keep history
            event_code = data.get("eventCode", "")
            if event_code and event_code != "NULL":
                event_entry = {
                    "code": event_code,
                    "eventName": EVENT_CODES.get(event_code, event_code),
                    "details": data.get("details", {}),
                    "time": time.strftime("%H:%M:%S")
                }
                self.data[packet_type]["eventHistory"].insert(0, event_entry)
                # Keep only last 10 events
                self.data[packet_type]["eventHistory"] = self.data[packet_type]["eventHistory"][:10]
        else:
            self.data[packet_type] = data
            
        self.last_update = time.time()
        
    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information"""
        session = self.data.get("session", {})
        return {
            "trackName": session.get("trackName", "Unknown"),
            "sessionTypeName": session.get("sessionTypeName", "Unknown"),
            "weatherName": session.get("weatherName", "Clear"),
            "trackTemperature": session.get("trackTemperature", 0),
            "airTemperature": session.get("airTemperature", 0),
            "sessionTimeLeftFormatted": session.get("sessionTimeLeftFormatted", "00:00"),
            "totalLaps": session.get("totalLaps", 0),
            "trackLengthKm": session.get("trackLengthKm", 0),
            "lastUpdate": self.last_update
        }
        
    def get_race_standings(self, limit: int = 22) -> List[Dict[str, Any]]:
        """Get current race standings with all drivers"""
        standings = []
        
        participants = self.data.get("participants", {}).get("participants", [])
        lap_data = self.data.get("lap_data", {}).get("laps", [])
        
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
                    "isPlayer": i == self.player_car_index,
                    "penalties": lap.get("penaltiesFormatted", "None"),
                    "pitStatus": lap.get("pitStatusName", "None")
                }
                standings.append(driver_info)
                
        # Sort by position
        standings.sort(key=lambda x: x["position"] if x["position"] > 0 else 999)
        return standings[:limit]
        
    def get_player_telemetry(self) -> Dict[str, Any]:
        """Get detailed telemetry for the player's car"""
        car_index = self.player_car_index
        
        # Get telemetry data
        telemetry = {}
        if self.data.get("car_telemetry", {}).get("carTelemetry"):
            tel_data = self.data["car_telemetry"]["carTelemetry"]
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
        if self.data.get("car_status", {}).get("carStatus"):
            status_data = self.data["car_status"]["carStatus"]
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
                    "flagColor": stat.get("flagColor", "None")
                }
        
        return {
            "carIndex": car_index,
            "telemetry": telemetry,
            "status": status,
            "lastUpdate": self.last_update
        }
        
    def get_recent_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent race events"""
        events = self.data.get("event", {}).get("eventHistory", [])
        return events[:limit]


# Initialize telemetry capture
telemetry_capture = F1TelemetryCapture()

# Create Flask app for HTTP MCP server
app = Flask(__name__)
CORS(app)

# MCP Tool definitions
MCP_TOOLS = [
    {
        "name": "get_session_info",
        "description": "Get current F1 session information including track, weather, and session details",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_race_standings",
        "description": "Get current race standings with all drivers, positions, and timing data",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of drivers to return (default: 22)",
                    "default": 22
                }
            },
            "required": []
        }
    },
    {
        "name": "get_player_telemetry",
        "description": "Get comprehensive telemetry data for the player's car including speed, temperatures, fuel, and damage",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_recent_events",
        "description": "Get recent race events like penalties, fastest laps, retirements, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to return (default: 5)",
                    "default": 5
                }
            },
            "required": []
        }
    },
    {
        "name": "get_race_summary",
        "description": "Get a comprehensive race summary including session info, top drivers, player status, and recent events",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


@app.route('/mcp/list_tools', methods=['POST'])
def list_tools():
    """MCP endpoint to list available tools"""
    return jsonify({
        "tools": MCP_TOOLS
    })


@app.route('/mcp/call_tool', methods=['POST'])
def call_tool():
    """MCP endpoint to call a specific tool"""
    data = request.get_json()
    tool_name = data.get('name')
    arguments = data.get('arguments', {})
    
    try:
        if tool_name == "get_session_info":
            result = telemetry_capture.get_session_info()
            
        elif tool_name == "get_race_standings":
            limit = arguments.get("limit", 22)
            result = telemetry_capture.get_race_standings(limit)
            
        elif tool_name == "get_player_telemetry":
            result = telemetry_capture.get_player_telemetry()
            
        elif tool_name == "get_recent_events":
            limit = arguments.get("limit", 5)
            result = telemetry_capture.get_recent_events(limit)
            
        elif tool_name == "get_race_summary":
            result = {
                "session": telemetry_capture.get_session_info(),
                "topDrivers": telemetry_capture.get_race_standings(5),
                "playerCar": telemetry_capture.get_player_telemetry(),
                "recentEvents": telemetry_capture.get_recent_events(3)
            }
            
        else:
            return jsonify({
                "error": f"Unknown tool: {tool_name}"
            }), 400
            
        return jsonify({
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        })
        
    except Exception as e:
        logger.error(f"Error calling tool {tool_name}: {e}")
        return jsonify({
            "error": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "telemetry_active": telemetry_capture.running,
        "last_update": telemetry_capture.last_update
    })


def main():
    """Main entry point for the HTTP MCP Server"""
    # Start telemetry capture
    telemetry_capture.start_capture()
    
    try:
        # Run the Flask HTTP server
        app.run(host='0.0.0.0', port=8000, debug=False)
    finally:
        # Clean up
        telemetry_capture.stop_capture()


if __name__ == "__main__":
    main()