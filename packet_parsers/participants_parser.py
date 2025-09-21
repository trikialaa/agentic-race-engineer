
import struct
import sys
import os
from .packet_header_parser import read_cstring

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (TEAM_NAMES, DRIVER_NAMES, NATIONALITY_NAMES)

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_participants(buf: memoryview):
    """
    Decode F1 22 participants packet with human-readable team, driver, and nationality names.
    """
    offset = _HDR_SIZE
    numActiveCars = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    participants = []
    
    for i in range(22):
        aiControlled = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        driverId = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        networkId = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        teamId = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        myTeam = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        raceNumber = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        nationality = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        name_bytes = bytes(buf[offset:offset+48]); offset += 48
        name = read_cstring(name_bytes)
        yourTelemetry = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        
        # Determine display name (use custom name if available, otherwise driver name)
        display_name = name if name else DRIVER_NAMES.get(driverId, f"Driver {driverId}")
        
        participant_data = {
            "carIndex": i,
            "aiControlled": bool(aiControlled),
            "controlType": "AI" if aiControlled else "Human",
            "driverId": driverId,
            "driverName": DRIVER_NAMES.get(driverId, f"Unknown Driver ({driverId})"),
            "networkId": networkId,
            "teamId": teamId,
            "teamName": TEAM_NAMES.get(teamId, f"Unknown Team ({teamId})"),
            "myTeam": bool(myTeam),
            "raceNumber": raceNumber,
            "nationality": nationality,
            "nationalityName": NATIONALITY_NAMES.get(nationality, f"Unknown ({nationality})"),
            "name": name,
            "displayName": display_name,
            "yourTelemetry": yourTelemetry,
            "telemetryRestricted": yourTelemetry == 0,
        }
        participants.append(participant_data)
    
    return {
        "numActiveCars": numActiveCars,
        "participants": participants,
        "activeCars": [p for p in participants if p["carIndex"] < numActiveCars]
    }