# f1_udp_full_parser.py
"""
Full F1 2022 UDP parser - decodes all packet types per the spec attached.
Outputs newline-delimited JSON for each received packet.

Spec source: "Data Output from F1 22 v16.docx" (attached). :contentReference[oaicite:9]{index=9}
"""

import argparse
import socket
import json
import sys
import time
from dataclasses import asdict

from packet_parsers import *


DECODERS = {
    0: decode_motion,
    1: decode_session,
    2: decode_lap_data,
    3: decode_event,
    4: decode_participants,
    5: decode_car_setups,
    6: decode_car_telemetry,
    7: decode_car_status,
    8: decode_final_classification,
    9: decode_lobby_info,
    10: decode_car_damage,
    11: decode_session_history,
}

DECODERS_PRINTS = {
    0: "motion",
    1: "session",
    2: "lap_data",
    3: "event",
    4: "participants",
    5: "car_setups",
    6: "car_telemetry",
    7: "car_status",
    8: "final_classification",
    9: "lobby_info",
    10: "car_damage",
    11: "session_history",
}

# ---------------- UDP loop ----------------
def run(bind_ip: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, port))
    print(f"Listening on {bind_ip}:{port}", file=sys.stderr)
    while True:
        data, addr = sock.recvfrom(8192)
        buf = memoryview(data)
        try:
            hdr = PacketHeader.from_buf(buf)
            pid = hdr.m_packetId
            decoder = DECODERS.get(pid)
            payload = {"note": "no decoder available"}
            if decoder:
                start_time = time.perf_counter_ns()
                payload = decoder(buf)
                end_time = time.perf_counter_ns()
                parsing_time_ms = (end_time - start_time) / 1_000_000  # Convert ns to ms
            # out = {
            #     "from": f"{addr[0]}:{addr[1]}",
            #     "header": asdict(hdr),
            #     "packetName": PACKET_ID.get(pid, f"Unknown({pid})"),
            #     "sizeBytes": len(data),
            #     "payload": payload
            # }
            # print(f"Detected packet of type {DECODERS_PRINTS[pid]}: Parsing took {parsing_time_ms:.3f} ms")
            if pid in [3]:
                print(json.dumps(payload))
        except Exception as e:
            print(f"Error decoding packet of type {DECODERS_PRINTS[pid]}: {e}")
            # print(json.dumps({"error": str(e), "sizeBytes": len(data), "rawHex": data.hex()}), file=sys.stderr)

# ---------------- CLI ----------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=20777)
    args = ap.parse_args()
    run(args.ip, args.port)
