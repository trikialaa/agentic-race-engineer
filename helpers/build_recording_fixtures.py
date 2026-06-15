#!/usr/bin/env python3
"""
Slice recording telemetry.bin files down to eval-sized fixtures.

Creates one compact fixture per recording session, covering only the packets
needed to reach the scenario frames used by evals/scenarios.py.

Run: python helpers/build_recording_fixtures.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RECORDINGS = ROOT / "recordings"
OUT_DIR = ROOT / "tests" / "fixtures"

HDR_FMT = "<HBBBBBQfIIBB"
HDR_SIZE = struct.calcsize(HDR_FMT)

# Drop IDs confirmed unused by query.py
DROP_IDS = {0, 5}
KEEP_ALL_IDS = {1, 3, 4, 8, 9, 14}
SNAPSHOT_IDS = {2, 6, 7, 10, 12, 13, 15}
SNAPSHOT_KEEP_EVERY_N = 30
SESSION_HISTORY_KEEP_EVERY_N = 15

# Sessions to build fixtures for; keys are session dir names
# Each entry: (output_stem, max_frame_needed, scenario_frames)
SESSIONS: dict[str, tuple[str, int, list[int]]] = {
    "20260611_183537": (
        "rec_session_a",
        22300,
        [8566, 15489, 22300],
    ),
    "20260611_203103": (
        "rec_session_b",
        28095,
        [3775, 8747, 19128, 20658, 28095],
    ),
    "20260613_173854": (
        "rec_session_c",
        30000,
        [9494, 13866, 14182, 21774, 22303, 25449, 25907, 28562, 28787],
    ),
    "20260614_205944": (
        "rec_session_d",
        18600,
        [1459, 7533, 7848, 8342, 18512],
    ),
}


_FRAME_OFFSET = struct.calcsize("<HBBBBBQf")  # offset of m_frameIdentifier = 19


def read_packets_up_to(path: Path, max_frame: int) -> list[bytes]:
    data = path.read_bytes()
    pos = 0
    pkts = []
    while pos + 2 <= len(data):
        length = int.from_bytes(data[pos : pos + 2], "little")
        pos += 2
        if pos + length > len(data):
            break
        pkt = data[pos : pos + length]
        pos += length
        if len(pkt) >= HDR_SIZE:
            frame = struct.unpack_from("<I", pkt, _FRAME_OFFSET)[0]
            if frame > max_frame:
                break
        pkts.append(pkt)
    return pkts


def downsample(pkts: list[bytes], marker_frames: set[int]) -> list[bytes]:
    from collections import defaultdict

    # Pre-scan: last index of each (pid, marker_frame) for forced inclusion
    last_before: dict[tuple[int, int], int] = {}
    for i, pkt in enumerate(pkts):
        if len(pkt) < HDR_SIZE:
            continue
        pid = struct.unpack_from("<B", pkt, 6)[0]
        frame = struct.unpack_from("<I", pkt, _FRAME_OFFSET)[0]
        if pid not in SNAPSHOT_IDS and pid != 11:
            continue
        for mf in marker_frames:
            if frame <= mf:
                last_before[(pid, mf)] = i
    forced = set(last_before.values())

    result = []
    snap_ctr: dict[int, int] = defaultdict(int)
    for i, pkt in enumerate(pkts):
        if len(pkt) < HDR_SIZE:
            continue
        pid = struct.unpack_from("<B", pkt, 6)[0]
        if pid in DROP_IDS:
            continue
        if pid in KEEP_ALL_IDS:
            result.append(pkt)
        elif pid == 11:
            if i in forced or snap_ctr[pid] % SESSION_HISTORY_KEEP_EVERY_N == 0:
                result.append(pkt)
            snap_ctr[pid] += 1
        elif pid in SNAPSHOT_IDS:
            if i in forced or snap_ctr[pid] % SNAPSHOT_KEEP_EVERY_N == 0:
                result.append(pkt)
            snap_ctr[pid] += 1
    return result


def write_bin(pkts: list[bytes], path: Path) -> int:
    total = 0
    with path.open("wb") as f:
        for pkt in pkts:
            f.write(len(pkt).to_bytes(2, "little"))
            f.write(pkt)
            total += 2 + len(pkt)
    return total


def main():
    for session_id, (out_stem, max_frame, scenario_frames) in SESSIONS.items():
        session_dir = RECORDINGS / session_id
        telemetry_bin = session_dir / "telemetry.bin"
        out_path = OUT_DIR / f"{out_stem}.bin"

        if not telemetry_bin.exists():
            print(f"SKIP {session_id}: telemetry.bin not found")
            continue

        size_mb = telemetry_bin.stat().st_size / 1e6
        print(f"\nSession {session_id} ({size_mb:.0f} MB)  max_frame={max_frame}")
        print(f"  Reading up to frame {max_frame}...")
        pkts = read_packets_up_to(telemetry_bin, max_frame)
        print(f"  {len(pkts)} packets read")

        print(f"  Downsampling (keep_every={SNAPSHOT_KEEP_EVERY_N})...")
        slim = downsample(pkts, set(scenario_frames))

        out_size = write_bin(slim, out_path)
        print(f"  {len(slim)} packets → {out_path.name}  ({out_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
