import struct
from dataclasses import dataclass

# ---------------- Header ----------------
# PacketHeader:
# uint16 m_packetFormat
# uint8  m_gameMajorVersion
# uint8  m_gameMinorVersion
# uint8  m_packetVersion
# uint8  m_packetId
# uint64 m_sessionUID
# float  m_sessionTime
# uint32 m_frameIdentifier
# uint8  m_playerCarIndex
# uint8  m_secondaryPlayerCarIndex

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

PACKET_ID = {
    0: "Motion",
    1: "Session",
    2: "Lap Data",
    3: "Event",
    4: "Participants",
    5: "Car Setups",
    6: "Car Telemetry",
    7: "Car Status",
    8: "Final Classification",
    9: "Lobby Info",
    10: "Car Damage",
    11: "Session History",
}

def read_cstring(b: bytes) -> str:
    i = b.find(b'\x00')
    if i == -1:
        return b.decode('utf-8', errors='ignore')
    return b[:i].decode('utf-8', errors='ignore')

@dataclass
class PacketHeader:
    m_packetFormat: int
    m_gameMajorVersion: int
    m_gameMinorVersion: int
    m_packetVersion: int
    m_packetId: int
    m_sessionUID: int
    m_sessionTime: float
    m_frameIdentifier: int
    m_playerCarIndex: int
    m_secondaryPlayerCarIndex: int

    @classmethod
    def from_buf(cls, buf: memoryview):
        if len(buf) < _HDR_SIZE:
            raise ValueError("Buffer too small for header")
        vals = struct.unpack_from(_HDR_FMT, buf, 0)
        return cls(*vals)