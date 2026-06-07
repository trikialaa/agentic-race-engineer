#!/usr/bin/env python3
"""
Lightweight FastMCP entry point that wires the shared telemetry capture layer to the registered tools.
"""

import logging
import os
import sys
from pathlib import Path

from fastmcp import FastMCP

# Ensure `src.*` imports resolve when this file is executed directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load as load_config
from src.live_data_engine.capture import F1TelemetryCapture
from src.mcp.tools import register_mcp_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_cfg = load_config()
telemetry_capture = F1TelemetryCapture(port=_cfg.get("udpPort", 20777))
mcp = FastMCP("F1 Telemetry Server")
register_mcp_tools(mcp, telemetry_capture)


def main():
    """Start capturing F1 telemetry and run the FastMCP service."""
    import argparse

    parser = argparse.ArgumentParser(description="F1 25 Telemetry MCP Server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.getenv("F1_MCP_TRANSPORT", "stdio"),
        help="MCP transport mode: stdio for local process clients, http for remote clients",
    )
    parser.add_argument(
        "--udp-ip",
        default=os.getenv("F1_UDP_IP", telemetry_capture.bind_ip),
        help="UDP bind IP for telemetry",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=int(os.getenv("F1_UDP_PORT", str(telemetry_capture.port))),
        help="UDP port for telemetry",
    )
    parser.add_argument(
        "--host", default=os.getenv("F1_MCP_HOST", "127.0.0.1"), help="MCP server host"
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("F1_MCP_PORT", "20915")), help="MCP server port"
    )
    parser.add_argument(
        "--events-buffer",
        type=int,
        default=int(os.getenv("F1_EVENTS_BUFFER", str(telemetry_capture.events_buffer_size))),
        help="Max number of events to keep in memory",
    )
    args = parser.parse_args()

    telemetry_capture.bind_ip = args.udp_ip
    telemetry_capture.port = args.udp_port
    telemetry_capture.events_buffer_size = max(1, args.events_buffer)

    telemetry_capture.start_capture()
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
            return

        # Compatibility across FastMCP versions: try common HTTP transport labels.
        http_transports = ("streamable-http", "http")
        last_error = None
        for transport_name in http_transports:
            try:
                mcp.run(transport=transport_name, host=args.host, port=args.port)
                return
            except TypeError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("Failed to start HTTP MCP transport")
    finally:
        telemetry_capture.stop_capture()


if __name__ == "__main__":
    main()
