
import struct
import sys
import os

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import EVENT_CODES, PENALTY_TYPES, INFRINGEMENT_TYPES

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_event(buf: memoryview):
    """
    Decode F1 22 event packet with human-readable event names and penalty details.
    """
    offset = _HDR_SIZE
    code = struct.unpack_from("<4s", buf, offset)[0]; offset += 4
    c = code.decode('ascii', errors='ignore')
    
    # Get human-readable event name
    event_name = EVENT_CODES.get(c, f"Unknown ({c})")
    
    details = {}
    
    if c == "FTLP":  # Fastest Lap
        vehicleIdx, lapTime = struct.unpack_from("<Bf", buf, offset); offset += 5
        details = {
            "vehicleIdx": vehicleIdx, 
            "lapTime": lapTime,
            "lapTimeFormatted": f"{lapTime:.3f}s"
        }
    elif c in ["RTMT", "TMPT", "RCWN", "DTSV", "SGSV"]:  # Single vehicle events
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicleIdx}
    elif c == "PENA":  # Penalty
        fields = struct.unpack_from("<BBBBBBB", buf, offset); offset += 7
        penalty_type = fields[0]
        infringement_type = fields[1]
        details = {
            "penaltyType": penalty_type,
            "penaltyTypeName": PENALTY_TYPES.get(penalty_type, f"Unknown ({penalty_type})"),
            "infringementType": infringement_type,
            "infringementTypeName": INFRINGEMENT_TYPES.get(infringement_type, f"Unknown ({infringement_type})"),
            "vehicleIdx": fields[2],
            "otherVehicleIdx": fields[3],
            "time": fields[4],
            "lapNum": fields[5],
            "placesGained": fields[6],
        }
    elif c == "SPTP":  # Speed Trap
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        speed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        isOverall = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        isDriver = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fastestIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fastestSpeed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "vehicleIdx": vehicleIdx, 
            "speedKph": speed,
            "speedMph": speed * 0.621371,  # Convert to mph
            "isOverallFastestInSession": bool(isOverall),
            "isDriverFastestInSession": bool(isDriver),
            "fastestVehicleIdxInSession": fastestIdx,
            "fastestSpeedInSession": fastestSpeed,
            "fastestSpeedInSessionMph": fastestSpeed * 0.621371
        }
    elif c == "STLG":  # Start Lights
        numLights = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "numLights": numLights,
            "lightsDescription": f"{numLights} light{'s' if numLights != 1 else ''} showing"
        }
    elif c == "FLBK":  # Flashback
        flash_frame = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        flash_time = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "flashbackFrameIdentifier": flash_frame, 
            "flashbackSessionTime": flash_time,
            "flashbackTimeFormatted": f"{flash_time:.3f}s"
        }
    elif c == "BUTN":  # Button Status
        buttonFlags = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        details = {"buttonFlags": buttonFlags}
    else:
        # Unknown event: return raw bytes
        details = {"rawHex": bytes(buf[offset:]).hex()}
    
    return {
        "eventCode": c, 
        "eventName": event_name,
        "details": details
    }