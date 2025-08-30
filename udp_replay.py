# replay_f1_udp.py
import socket
import time
import sys

if len(sys.argv) < 2:
    print("Usage: python replay_f1_udp.py <capture_file>")
    sys.exit(1)

filename = sys.argv[1]
UDP_IP = "127.0.0.1"   # where to send (change if needed)
UDP_PORT = 20777       # port to send to

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print(f"Replaying {filename} to {UDP_IP}:{UDP_PORT}... (Ctrl+C to stop)")

with open(filename, "rb") as f:
    try:
        while True:
            # read packet length
            len_bytes = f.read(2)
            if not len_bytes:
                break
            length = int.from_bytes(len_bytes, "little")

            # read packet
            packet = f.read(length)
            if not packet:
                break

            # send packet
            sock.sendto(packet, (UDP_IP, UDP_PORT))

            # F1 sends ~20Hz, so sleep a bit
            time.sleep(1/20.0)

    except KeyboardInterrupt:
        print("\nStopped replay.")