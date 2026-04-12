import struct
import sys
import os
from .packet_header_parser import read_cstring

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (READY_STATUS, NATIONALITY_NAMES, TEAM_NAMES)

PLATFORM_NAMES = {
    1: "Steam",
    3: "PlayStation",
    4: "Xbox",
    6: "Origin",
    255: "Unknown"
}

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_lobby_info(buf: memoryview):
    offset = _HDR_SIZE
    numPlayers = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    players = []

    for i in range(22):
        aiControlled = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        teamId = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        nationality = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        platform = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        name_bytes = bytes(buf[offset:offset + 32]); offset += 32
        name = read_cstring(name_bytes)
        carNumber = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        yourTelemetry = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        showOnlineNames = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        techLevel = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        readyStatus = struct.unpack_from("<B", buf, offset)[0]; offset += 1

        players.append({
            "aiControlled": bool(aiControlled),
            "teamId": teamId,
            "teamName": TEAM_NAMES.get(teamId, f"Unknown Team ({teamId})"),
            "nationality": nationality,
            "nationalityName": NATIONALITY_NAMES.get(nationality, f"Unknown ({nationality})"),
            "platform": platform,
            "platformName": PLATFORM_NAMES.get(platform, f"Unknown ({platform})"),
            "name": name,
            "gaName": name,
            "carNumber": carNumber,
            "yourTelemetry": yourTelemetry,
            "showOnlineNames": bool(showOnlineNames),
            "techLevel": techLevel,
            "readyStatus": readyStatus,
            "readyStatusName": READY_STATUS.get(readyStatus, f"Unknown ({readyStatus})"),
        })

    return {"numPlayers": numPlayers, "players": players}
