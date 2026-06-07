# replay_f1_udp.py
import argparse
import os
import socket
import time

capture_dir = os.path.join("helpers", "udp_sampler", "capture_data")
default_capture = os.path.join(capture_dir, "f1_25_capture_20260412_151325.bin")

parser = argparse.ArgumentParser(description="Replay recorded F1 UDP packets.")
parser.add_argument(
    "filename",
    nargs="?",
    default=default_capture,
    help="Path to the capture file to replay.",
)
parser.add_argument(
    "--loop",
    action="store_true",
    help="Loop the replay continuously until interrupted.",
)
args = parser.parse_args()

UDP_IP = "127.0.0.1"  # where to send (change if needed)
UDP_PORT = 20777  # port to send to

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print(
    f"Replaying {args.filename} to {UDP_IP}:{UDP_PORT}... (Ctrl+C to stop){' (looping)' if args.loop else ''}"
)


def _replay_file():
    with open(args.filename, "rb") as f:
        while True:
            len_bytes = f.read(2)
            if not len_bytes:
                return
            length = int.from_bytes(len_bytes, "little")
            packet = f.read(length)
            if not packet:
                return
            sock.sendto(packet, (UDP_IP, UDP_PORT))
            time.sleep(1 / 120.0)


try:
    while True:
        _replay_file()
        if not args.loop:
            break
        print("Looping replay...")
except KeyboardInterrupt:
    print("\nStopped replay.")
