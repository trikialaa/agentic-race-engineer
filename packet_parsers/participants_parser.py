
import struct
from .packet_header_parser import read_cstring

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_participants(buf: memoryview):
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
        participants.append({
            "aiControlled": aiControlled,
            "driverId": driverId,
            "networkId": networkId,
            "teamId": teamId,
            "myTeam": myTeam,
            "raceNumber": raceNumber,
            "nationality": nationality,
            "name": name,
            "yourTelemetry": yourTelemetry,
        })
    return {"numActiveCars": numActiveCars, "participants": participants}