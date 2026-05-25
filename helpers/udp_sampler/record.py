# capture_f1_udp.py
import os
import socket
import datetime

UDP_IP = "0.0.0.0"  # listen on all interfaces
UDP_PORT = 20777    # default port for F1 25 telemetry

capture_dir = os.path.join("helpers", "udp_sampler", "capture_data")
os.makedirs(capture_dir, exist_ok=True)

# file to save raw packets
filename = os.path.join(
    capture_dir,
    f"f1_25_capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.bin",
)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Listening for F1 25 telemetry on {UDP_IP}:{UDP_PORT}")
print(f"Saving to {filename}... (press Ctrl+C to stop)")

with open(filename, "wb") as f:
    try:
        while True:
            data, addr = sock.recvfrom(2048)  # max packet size
            f.write(len(data).to_bytes(2, "little"))  # store packet length
            f.write(data)  # store packet
    except KeyboardInterrupt:
        print("\nStopped capture.")
