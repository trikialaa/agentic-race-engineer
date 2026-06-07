"""Launch both the Flask transcription server and the Electron UI together."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional

from werkzeug.serving import make_server

from src.config import load as load_config
from src.web import web_transcribe_server

ROOT = Path(__file__).resolve().parent


def _ensure_npm_available() -> str:
    npm_bin = shutil.which("npm")
    if not npm_bin:
        raise RuntimeError(
            "npm was not found in PATH. Install Node.js/npm before running the Electron shell."
        )
    return npm_bin


def _start_http_server(host: str, port: int):
    """Create and start the Flask server in a background thread."""
    server = make_server(host, port, web_transcribe_server.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _wait_for_server_ready(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"HTTP server on {host}:{port} did not become ready within {timeout}s.")


def _launch_electron(
    command: Iterable[str], cwd: Path, env_overrides: Optional[dict[str, str]] = None
) -> subprocess.Popen:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.Popen(list(command), cwd=str(cwd), env=env)


def _ask_restart() -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        resp = input("Restart both services? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return resp.startswith("y")


def _run_stack(
    host: str,
    port: int,
    electron_command: List[str],
    electron_cwd: Path,
    skip_electron: bool,
) -> int:
    web_transcribe_server.ensure_agent_ready()
    http_server, server_thread = _start_http_server(host, port)
    _wait_for_server_ready(host, port)
    electron_proc: Optional[subprocess.Popen] = None

    try:
        if not skip_electron:
            electron_proc = _launch_electron(
                electron_command,
                electron_cwd,
                {"F1_RADIO_URL": f"http://{host}:{port}"},
            )

        while electron_proc and electron_proc.poll() is None:
            try:
                electron_proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                continue
        if electron_proc:
            return electron_proc.returncode or 0
        return 0
    except KeyboardInterrupt:
        if electron_proc and electron_proc.poll() is None:
            electron_proc.terminate()
            try:
                electron_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                electron_proc.kill()
        raise
    finally:
        http_server.shutdown()
        server_thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description="Start the race engineer UI stack.")
    _cfg = load_config()
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host for the Flask server.")
    parser.add_argument("--port", type=int, default=_cfg.get("serverPort", 8080), help="HTTP port for the Flask server.")
    parser.add_argument(
        "--electron-cmd",
        nargs="+",
        default=["npm", "run", "start:electron"],
        help="Command to launch the Electron shell.",
    )
    parser.add_argument(
        "--electron-cwd",
        type=Path,
        default=ROOT,
        help="Working directory for the Electron shell.",
    )
    parser.add_argument(
        "--skip-electron",
        action="store_true",
        help="Only start the Flask server (useful for testing the REST API).",
    )
    args = parser.parse_args()

    try:
        if not args.skip_electron:
            _ensure_npm_available()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    while True:
        try:
            _run_stack(args.host, args.port, args.electron_cmd, args.electron_cwd, args.skip_electron)
        except KeyboardInterrupt:
            break
        if args.skip_electron:
            break
        if not _ask_restart():
            break


if __name__ == "__main__":
    main()
