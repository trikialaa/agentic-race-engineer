"""In-process fixture replay loader shared by tests and the MCP server's fixture mode."""

from __future__ import annotations

import struct
from pathlib import Path

_LEN_FMT = "<H"
_LEN_SIZE = struct.calcsize(_LEN_FMT)

HDR_FMT = "<HBBBBBQfIIBB"
HDR_SIZE = struct.calcsize(HDR_FMT)


def _read_packets(bin_path: Path) -> list[bytes]:
    data = bin_path.read_bytes()
    pos = 0
    pkts = []
    while pos + _LEN_SIZE <= len(data):
        (length,) = struct.unpack_from(_LEN_FMT, data, pos)
        pos += _LEN_SIZE
        if pos + length > len(data):
            break
        pkts.append(data[pos : pos + length])
        pos += length
    return pkts


def replay_fixture_into(capture, bin_path: Path, frame: int | None = None) -> None:
    """Feed fixture packets into *capture* up to *frame* (inclusive).

    No UDP socket or background thread is started. Uses the same
    PacketHeader.from_buf + PACKET_TYPES decoder path as the live listener.
    """
    from src.live_data_engine.capture import PACKET_TYPES
    from src.udp_parser import PacketHeader

    for pkt in _read_packets(bin_path):
        if len(pkt) < HDR_SIZE:
            continue
        buf = memoryview(pkt)
        try:
            hdr = PacketHeader.from_buf(buf)
        except Exception:
            continue
        if frame is not None and hdr.m_frameIdentifier > frame:
            break
        capture.player_car_index = hdr.m_playerCarIndex
        pid = hdr.m_packetId
        if pid in PACKET_TYPES:
            name, decoder = PACKET_TYPES[pid]
            try:
                capture._update_data(name, decoder(buf))
            except Exception:
                pass
