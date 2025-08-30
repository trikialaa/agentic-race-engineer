
import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_event(buf: memoryview):
    # PacketEventData: header + 4-byte event string code + union details (40 bytes total event packet per spec). :contentReference[oaicite:13]{index=13}
    offset = _HDR_SIZE
    code = struct.unpack_from("<4s", buf, offset)[0]; offset += 4
    c = code.decode('ascii', errors='ignore')
    details = {}
    if c == "FTLP":
        vehicleIdx, lapTime = struct.unpack_from("<Bf", buf, offset); offset += 5
        details = {"vehicleIdx": vehicleIdx, "lapTime": lapTime}
    elif c == "RTMT":
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicleIdx}
    elif c == "TMPT":
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicleIdx}
    elif c == "RCWN":
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicleIdx}
    elif c == "PENA":
        fields = struct.unpack_from("<BBBBBBB", buf, offset); offset += 7
        details = {
            "penaltyType": fields[0],
            "infringementType": fields[1],
            "vehicleIdx": fields[2],
            "otherVehicleIdx": fields[3],
            "time": fields[4],
            "lapNum": fields[5],
            "placesGained": fields[6],
        }
    elif c == "SPTP":
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        speed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        isOverall = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        isDriver = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fastestIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fastestSpeed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {
            "vehicleIdx": vehicleIdx, "speedKph": speed,
            "isOverallFastestInSession": bool(isOverall),
            "isDriverFastestInSession": bool(isDriver),
            "fastestVehicleIdxInSession": fastestIdx,
            "fastestSpeedInSession": fastestSpeed
        }
    elif c == "STLG":
        numLights = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"numLights": numLights}
    elif c == "DTSV":
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicleIdx}
    elif c == "SGSV":
        vehicleIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        details = {"vehicleIdx": vehicleIdx}
    elif c == "FLBK":
        flash_frame = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        flash_time = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        details = {"flashbackFrameIdentifier": flash_frame, "flashbackSessionTime": flash_time}
    elif c == "BUTN":
        buttonFlags = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        details = {"buttonFlags": buttonFlags}
    else:
        # unknown: return raw bytes
        details = {"rawHex": bytes(buf[offset:]).hex()}
    return {"eventCode": c, "details": details}