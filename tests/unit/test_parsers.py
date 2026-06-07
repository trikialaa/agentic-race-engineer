"""Unit tests for packet parsers using real bytes from the fixture."""

from __future__ import annotations

import struct
from pathlib import Path

FIXTURE_BIN = Path(__file__).parents[1] / "fixtures" / "race_catalunya_2025.bin"
HDR_FMT = "<HBBBBBQfIIBB"
HDR_SIZE = struct.calcsize(HDR_FMT)


def _iter_packets():
    data = FIXTURE_BIN.read_bytes()
    pos = 0
    while pos + 2 <= len(data):
        length = int.from_bytes(data[pos : pos + 2], "little")
        pos += 2
        if pos + length > len(data):
            break
        yield data[pos : pos + length]
        pos += length


def _first_packet_by_id(pid: int) -> bytes:
    for pkt in _iter_packets():
        if len(pkt) > 6 and pkt[6] == pid:
            return pkt
    raise ValueError(f"No packet with pid={pid} in fixture")


class TestPacketHeader:
    def test_header_parses_from_fixture(self):
        from src.udp_parser import PacketHeader

        pkt = next(_iter_packets())
        hdr = PacketHeader.from_buf(memoryview(pkt))
        assert hdr.m_packetFormat == 2025
        assert hdr.m_gameYear == 25
        assert 0 <= hdr.m_packetId <= 15
        assert hdr.m_frameIdentifier >= 0
        assert 0 <= hdr.m_playerCarIndex < 22

    def test_all_packets_have_valid_headers(self):
        from src.udp_parser import PacketHeader

        errors = 0
        for pkt in _iter_packets():
            if len(pkt) < HDR_SIZE:
                continue
            try:
                hdr = PacketHeader.from_buf(memoryview(pkt))
                assert 0 <= hdr.m_packetId <= 15
            except Exception:
                errors += 1
        assert errors == 0


class TestEventParser:
    def test_event_packet_decodes(self):
        from src.udp_parser.packet_parsers.event_parser import decode_event

        pkt = _first_packet_by_id(3)
        result = decode_event(memoryview(pkt))
        assert "eventCode" in result
        code = result["eventCode"]
        assert isinstance(code, str) and len(code) == 4

    def test_ssta_event_present(self):
        from src.udp_parser.packet_parsers.event_parser import decode_event

        codes_seen = set()
        for pkt in _iter_packets():
            if len(pkt) > 6 and pkt[6] == 3:
                r = decode_event(memoryview(pkt))
                codes_seen.add(r.get("eventCode", ""))
        assert "SSTA" in codes_seen  # Session started


class TestLapDataParser:
    def test_lap_data_has_laps_list(self):
        from src.udp_parser.packet_parsers.lap_data_parser import decode_lap_data

        pkt = _first_packet_by_id(2)
        result = decode_lap_data(memoryview(pkt))
        assert "laps" in result
        assert isinstance(result["laps"], list)
        assert len(result["laps"]) >= 1

    def test_lap_entries_have_position_field(self):
        from src.udp_parser.packet_parsers.lap_data_parser import decode_lap_data

        pkt = _first_packet_by_id(2)
        result = decode_lap_data(memoryview(pkt))
        laps = result["laps"]
        for entry in laps:
            if isinstance(entry, dict):
                assert "carPosition" in entry
                break


class TestParticipantsParser:
    def test_participants_has_participant_list(self):
        from src.udp_parser.packet_parsers.participants_parser import decode_participants

        pkt = _first_packet_by_id(4)
        result = decode_participants(memoryview(pkt))
        assert "participants" in result
        assert isinstance(result["participants"], list)
        assert len(result["participants"]) >= 1

    def test_participant_has_name_field(self):
        from src.udp_parser.packet_parsers.participants_parser import decode_participants

        pkt = _first_packet_by_id(4)
        result = decode_participants(memoryview(pkt))
        parts = result["participants"]
        named = [p for p in parts if isinstance(p, dict) and p.get("name")]
        assert len(named) > 0
