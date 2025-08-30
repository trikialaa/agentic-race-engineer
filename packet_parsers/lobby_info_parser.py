
import struct
from .packet_header_parser import read_cstring

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_lobby_info(buf: memoryview):
    offset = _HDR_SIZE
    numPlayers = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    players = []
    for i in range(22):
        aiControlled = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        teamId = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        nationality = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        name_bytes = bytes(buf[offset:offset+48]); offset += 48
        name = read_cstring(name_bytes)
        carNumber = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        readyStatus = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        players.append({
            "aiControlled": aiControlled, "teamId": teamId, "nationality": nationality,
            "name": name, "carNumber": carNumber, "readyStatus": readyStatus
        })
    return {"numPlayers": numPlayers, "players": players}