"""
Fixture builder — dev-time only. Requires the 70 MB source capture at
helpers/udp_sampler/capture_data/. Produces:
  tests/fixtures/race_catalunya_2025.bin   (~1-3 MB downsampled slice)
  tests/fixtures/markers.json              (named frame offsets)
  tests/fixtures/golden/                   (masked tool outputs)

Run: python tests/fixtures/build_fixture.py [--source /path/to/other.bin]
     python tests/fixtures/build_fixture.py --update-golden
     python tests/fixtures/build_fixture.py --skip-parity   (faster rebuild)
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DEFAULT_SOURCE = (
    ROOT / "helpers" / "udp_sampler" / "capture_data" / "f1_25_capture_20260412_151325.bin"
)
OUT_BIN = Path(__file__).parent / "race_catalunya_2025.bin"
OUT_MARKERS = Path(__file__).parent / "markers.json"
OUT_GOLDEN = Path(__file__).parent / "golden"

HDR_FMT = "<HBBBBBQfIIBB"
HDR_SIZE = struct.calcsize(HDR_FMT)

# Packet IDs to drop entirely — confirmed unread by query.py
DROP_IDS = {0, 5}  # motion, car_setups

# Low-frequency / critical — keep every packet
KEEP_ALL_IDS = {1, 3, 4, 8, 9, 14}  # session, event, participants, final_class, lobby, time_trial

# session_history (pid=11): high-frequency per-car data, needed for get_lap_times invariants.
# Keep every Nth — much denser than other snapshots so lap_times has usable data.
SESSION_HISTORY_KEEP_EVERY_N = 15

# Remaining high-frequency snapshot types (latest-wins): thin more aggressively
SNAPSHOT_IDS = {
    2,
    6,
    7,
    10,
    12,
    13,
    15,
}  # lap_data, car_telemetry, car_status, car_damage, tyre_sets, motion_ex, lap_pos
SNAPSHOT_KEEP_EVERY_N = 30

# Tools where golden comparison is reliable (pure latest-snapshot reads, no wall-clock or
# accumulator state). get_lap_times and get_recent_events are deliberately excluded:
# get_lap_times depends on session_history_by_car accumulation that can't survive thinning;
# get_recent_events depends on wall-clock dedup at ingest time.
PARITY_GOLDEN_TOOLS = (
    "get_context_frame",
    "get_leaderboard",
    "get_weather_forecast",
    "get_strategy",
)

# Markers: event codes → scenario names
MARKER_EVENTS = {
    "LGOT": "start",
    "FTLP": "green_steady",
    "CHQF": "finish",
}
FRAME_MARKER_MID = 5000  # synthetic mid-race


def read_packets(path: Path) -> list[bytes]:
    data = path.read_bytes()
    pos = 0
    pkts = []
    while pos + 2 <= len(data):
        length = int.from_bytes(data[pos : pos + 2], "little")
        pos += 2
        if pos + length > len(data):
            break
        pkts.append(data[pos : pos + length])
        pos += length
    return pkts


def parse_header(pkt: bytes) -> tuple | None:
    if len(pkt) < HDR_SIZE:
        return None
    return struct.unpack_from(HDR_FMT, pkt, 0)


def pid_frame(pkt: bytes) -> tuple[int, int]:
    hdr = parse_header(pkt)
    if hdr is None:
        return -1, -1
    return hdr[5], hdr[8]


def get_event_code(pkt: bytes) -> str | None:
    if len(pkt) < HDR_SIZE + 4:
        return None
    return pkt[HDR_SIZE : HDR_SIZE + 4].decode("ascii", errors="ignore")


def discover_markers(pkts: list[bytes]) -> dict:
    markers: dict[str, int] = {"mid_strategy": FRAME_MARKER_MID}
    for pkt in pkts:
        hdr = parse_header(pkt)
        if hdr is None:
            continue
        pid, frame = hdr[5], hdr[8]
        if pid == 3:
            code = get_event_code(pkt)
            if code in MARKER_EVENTS and MARKER_EVENTS[code] not in markers:
                markers[MARKER_EVENTS[code]] = frame
        if len(markers) == 4:
            break
    return markers


def downsample(pkts: list[bytes], marker_frames: set[int]) -> list[bytes]:
    # Pre-scan: find last packet index per (pid, marker_frame) for forced inclusion
    last_before: dict[tuple[int, int], int] = {}
    for i, pkt in enumerate(pkts):
        hdr = parse_header(pkt)
        if hdr is None:
            continue
        pid, frame = hdr[5], hdr[8]
        if pid not in SNAPSHOT_IDS and pid != 11:
            continue
        for mf in marker_frames:
            if frame <= mf:
                last_before[(pid, mf)] = i
    forced = set(last_before.values())

    result = []
    snap_ctr: dict[int, int] = defaultdict(int)
    for i, pkt in enumerate(pkts):
        hdr = parse_header(pkt)
        if hdr is None:
            continue
        pid = hdr[5]
        if pid in DROP_IDS:
            continue
        if pid in KEEP_ALL_IDS:
            result.append(pkt)
        elif pid == 11:  # session_history: denser keep
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


def load_capture_from_pkts(pkts: list[bytes]):
    from src.live_data_engine.capture import PACKET_TYPES, F1TelemetryCapture
    from src.udp_parser import PacketHeader

    cap = F1TelemetryCapture()
    for pkt in pkts:
        buf = memoryview(pkt)
        try:
            hdr = PacketHeader.from_buf(buf)
        except Exception:
            continue
        cap.player_car_index = hdr.m_playerCarIndex
        pid = hdr.m_packetId
        if pid in PACKET_TYPES:
            name, decoder = PACKET_TYPES[pid]
            try:
                payload = decoder(buf)
                cap._update_data(name, payload)
            except Exception:
                pass
    return cap


def mask_for_compare(obj):
    """Strip wall-clock and transient fields before comparing tool outputs."""
    MASK_KEYS = {"time", "serverTime", "ts", "mode"}
    if isinstance(obj, dict):
        return {k: mask_for_compare(v) for k, v in obj.items() if k not in MASK_KEYS}
    if isinstance(obj, list):
        return [mask_for_compare(v) for v in obj]
    return obj


def _reset_lap_times_state() -> None:
    import src.mcp.functions.lap_times as lt

    lt._LAP_TIMES_STATE.clear()
    lt._LAP_TIMES_SESSION_UID = None


def run_parity_tools(cap) -> dict:
    import src.mcp.functions as fns

    _reset_lap_times_state()
    results = {}
    for name in PARITY_GOLDEN_TOOLS:
        fn = getattr(fns, name)
        try:
            results[name] = fn(cap)
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def parity_check(source_pkts: list[bytes], slim_pkts: list[bytes], markers: dict) -> None:
    print("Running parity gate (4 pure-read tools)...")
    errors = []
    for marker_name, mf in sorted(markers.items(), key=lambda x: x[1]):
        src_up = [p for p in source_pkts if (h := parse_header(p)) is not None and h[8] <= mf]
        slim_up = [p for p in slim_pkts if (h := parse_header(p)) is not None and h[8] <= mf]

        src_cap = load_capture_from_pkts(src_up)
        slim_cap = load_capture_from_pkts(slim_up)

        src_out = run_parity_tools(src_cap)
        slim_out = run_parity_tools(slim_cap)

        marker_ok = True
        for tool_name in PARITY_GOLDEN_TOOLS:
            s = mask_for_compare(src_out[tool_name])
            d = mask_for_compare(slim_out.get(tool_name, {}))
            if s != d:
                marker_ok = False
                errors.append(f"  PARITY FAIL [{marker_name}][{tool_name}]")
                import difflib
                import pprint

                diff = list(
                    difflib.unified_diff(
                        pprint.pformat(s).splitlines(),
                        pprint.pformat(d).splitlines(),
                        fromfile="source",
                        tofile="slim",
                        lineterm="",
                    )
                )
                for line in diff[:50]:
                    errors.append("    " + line)
        print(f"  [{marker_name}] frame={mf} — {'OK' if marker_ok else 'FAIL'}")

    if errors:
        print("\nPARITY GATE FAILED:")
        for e in errors:
            print(e)
        sys.exit(1)
    print("Parity gate passed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--skip-parity", action="store_true", help="Skip parity gate")
    parser.add_argument(
        "--update-golden", action="store_true", help="Regenerate golden JSON fixtures"
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Source not found: {args.source}")
        sys.exit(1)

    print(f"Reading source ({args.source.stat().st_size / 1e6:.1f} MB)...")
    source_pkts = read_packets(args.source)
    print(f"  {len(source_pkts)} packets")

    print("Discovering markers...")
    markers = discover_markers(source_pkts)
    print(f"  {markers}")
    OUT_MARKERS.write_text(json.dumps(markers, indent=2))

    marker_frames = set(markers.values())
    print("Downsampling...")
    slim_pkts = downsample(source_pkts, marker_frames)
    size = write_bin(slim_pkts, OUT_BIN)
    print(f"  {len(slim_pkts)} packets, {size / 1e6:.2f} MB → {OUT_BIN}")
    if size > 3_500_000:
        print(f"  NOTE: fixture is {size / 1e6:.2f} MB (target ≤3.5 MB)")

    if not args.skip_parity:
        parity_check(source_pkts, slim_pkts, markers)

    if args.update_golden:
        print("Generating golden fixtures...")
        OUT_GOLDEN.mkdir(exist_ok=True)
        import src.mcp.functions as fns

        for scenario in ("start", "green_steady", "finish"):
            mf = markers.get(scenario)
            if mf is None:
                continue
            pkts_up = [p for p in slim_pkts if (h := parse_header(p)) is not None and h[8] <= mf]
            _reset_lap_times_state()
            cap = load_capture_from_pkts(pkts_up)
            for tool_name in PARITY_GOLDEN_TOOLS:
                fn = getattr(fns, tool_name)
                result = fn(cap)
                masked = mask_for_compare(result)
                out_path = OUT_GOLDEN / f"{tool_name}__{scenario}.json"
                out_path.write_text(json.dumps(masked, indent=2))
                print(f"  {out_path.name}")
        print("Golden fixtures written.")

    print("Done.")


if __name__ == "__main__":
    main()
