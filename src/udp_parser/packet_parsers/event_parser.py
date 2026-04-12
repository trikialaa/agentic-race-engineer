import struct
import sys
import os

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import EVENT_CODES, PENALTY_TYPES, INFRINGEMENT_TYPES

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

RETIREMENT_REASONS = {
    0: "Invalid",
    1: "Retired",
    2: "Finished",
    3: "Terminal damage",
    4: "Inactive",
    5: "Not enough laps completed",
    6: "Black flagged",
    7: "Red flagged",
    8: "Mechanical failure",
    9: "Session skipped",
    10: "Session simulated"
}

DRS_DISABLED_REASONS = {
    0: "Wet track",
    1: "Safety car deployed",
    2: "Red flag",
    3: "Min lap not reached"
}

SAFETY_CAR_TYPES = {
    0: "No Safety Car",
    1: "Full Safety Car",
    2: "Virtual Safety Car",
    3: "Formation Lap Safety Car"
}

SAFETY_CAR_EVENT_TYPES = {
    0: "Deployed",
    1: "Returning",
    2: "Returned",
    3: "Resume Race"
}


def decode_event(buf: memoryview):
    """
    Decode F1 25 event packet with detailed event-specific payloads.
    """
    offset = _HDR_SIZE
    code = struct.unpack_from("<4s", buf, offset)[0]; offset += 4
    event_code = code.decode("ascii", errors="ignore")
    event_name = EVENT_CODES.get(event_code, f"Unknown ({event_code})")
    details = {}

    if event_code == "FTLP":
        vehicle_idx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        lap_time = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "vehicleIdx": vehicle_idx,
            "lapTime": lap_time,
            "lapTimeFormatted": f"{lap_time:.3f}s"
        }
    elif event_code == "RTMT":
        vehicle_idx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        reason = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "vehicleIdx": vehicle_idx,
            "reason": reason,
            "reasonName": RETIREMENT_REASONS.get(reason, f"Unknown ({reason})")
        }
    elif event_code == "DRSD":
        reason = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "reason": reason,
            "reasonName": DRS_DISABLED_REASONS.get(reason, f"Unknown ({reason})")
        }
    elif event_code in {"TMPT", "RCWN", "DTSV"}:
        vehicle_idx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicle_idx}
    elif event_code == "SGSV":
        vehicle_idx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        stop_time = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "vehicleIdx": vehicle_idx,
            "stopTime": stop_time,
            "stopTimeFormatted": f"{stop_time:.3f}s"
        }
    elif event_code == "PENA":
        fields = struct.unpack_from("<BBBBBBB", buf, offset); offset += 7
        penalty_type, infringement_type = fields[0], fields[1]
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
    elif event_code == "SPTP":
        vehicle_idx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        speed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        is_overall = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        is_driver = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fastest_idx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fastest_speed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "vehicleIdx": vehicle_idx,
            "speedKph": speed,
            "speedMph": round(speed * 0.621371),
            "isOverallFastestInSession": bool(is_overall),
            "isDriverFastestInSession": bool(is_driver),
            "fastestVehicleIdxInSession": fastest_idx,
            "fastestSpeedInSession": fastest_speed,
            "fastestSpeedInSessionMph": round(fastest_speed * 0.621371)
        }
    elif event_code == "STLG":
        num_lights = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "numLights": num_lights,
            "lightsDescription": f"{num_lights} light{'s' if num_lights != 1 else ''} showing"
        }
    elif event_code == "FLBK":
        flash_frame = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        flash_time = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "flashbackFrameIdentifier": flash_frame,
            "flashbackSessionTime": flash_time,
            "flashbackTimeFormatted": f"{flash_time:.3f}s"
        }
    elif event_code == "BUTN":
        button_status = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        details = {"buttonFlags": button_status}
    elif event_code == "OVTK":
        overtak = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        overtaken = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "overtakingVehicleIdx": overtak,
            "beingOvertakenVehicleIdx": overtaken
        }
    elif event_code == "SCAR":
        safety_car_type = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        event_type = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "safetyCarType": safety_car_type,
            "safetyCarTypeName": SAFETY_CAR_TYPES.get(safety_car_type, f"Unknown ({safety_car_type})"),
            "eventType": event_type,
            "eventTypeName": SAFETY_CAR_EVENT_TYPES.get(event_type, f"Unknown ({event_type})")
        }
    elif event_code == "COLL":
        v1 = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        v2 = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {
            "vehicle1Idx": v1,
            "vehicle2Idx": v2
        }
    elif event_code == "RDFL":
        details = {}
    else:
        details = {"rawHex": bytes(buf[offset:]).hex()}

    return {
        "eventCode": event_code,
        "eventName": event_name,
        "details": details
    }
