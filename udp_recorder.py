# capture_f1_udp.py
import socket
import datetime

UDP_IP = "0.0.0.0"  # listen on all interfaces
UDP_PORT = 20777    # default port for F1 22 telemetry

# file to save raw packets
filename = f"f1_22_capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Listening for F1 22 telemetry on {UDP_IP}:{UDP_PORT}")
print(f"Saving to {filename}... (press Ctrl+C to stop)")

with open(filename, "wb") as f:
    try:
        while True:
            data, addr = sock.recvfrom(2048)  # max packet size
            f.write(len(data).to_bytes(2, "little"))  # store packet length
            f.write(data)  # store packet
    except KeyboardInterrupt:
        print("\nStopped capture.")