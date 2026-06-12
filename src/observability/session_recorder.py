"""Session recorder for internal testing.

When F1_RECORD_DIR is set, captures a time-aligned trace of one play session:
- raw UDP telemetry packets (telemetry.bin, replay-compatible with fixture_replay)
- per-packet index of (ts, frame) for wall-clock/frame correlation (telemetry_index.jsonl)
- mic audio blobs (audio/turn_NNNN.webm)
- per-turn transcript + response + context frame (interactions.jsonl)
- MCP tool calls (toolcalls.jsonl, via F1_MCP_TOOL_LOG)

The recorder is a no-op singleton when F1_RECORD_DIR is unset, so normal runs
and the test suite are completely unaffected.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PACKET_LEN_FMT = "<H"  # same as helpers/udp_sampler/record.py and fixture_replay.py


def _git_sha() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


class SessionRecorder:
    """Thread-safe session recorder. Constructed once per process from F1_RECORD_DIR."""

    def __init__(self, session_dir: Path) -> None:
        self._dir = session_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / "audio").mkdir(exist_ok=True)

        self._lock = threading.Lock()
        self._telemetry_file = open(self._dir / "telemetry.bin", "ab")
        self._telemetry_index = open(self._dir / "telemetry_index.jsonl", "a")
        self._interactions_file = open(self._dir / "interactions.jsonl", "a")

        # Pending turns: turn_id -> partial dict, finalized when /agent responds
        self._pending: dict[str, dict[str, Any]] = {}
        self._turn_counter = 0

        self._start_ts = time.time()
        logger.info("SessionRecorder: writing to %s", session_dir)

    # ── Telemetry side (called from MCP subprocess) ────────────────────────

    def record_packet(self, raw_bytes: bytes, ts: float, frame: int | None, packet_id: int) -> None:
        length_prefix = struct.pack(_PACKET_LEN_FMT, len(raw_bytes))
        index_line = json.dumps({"ts": ts, "frame": frame, "packetId": packet_id}) + "\n"
        with self._lock:
            self._telemetry_file.write(length_prefix + raw_bytes)
            self._telemetry_index.write(index_line)

    def flush_telemetry(self) -> None:
        with self._lock:
            self._telemetry_file.flush()
            self._telemetry_index.flush()

    # ── Flask side (called from web server per turn) ───────────────────────

    def next_turn_audio_path(self) -> tuple[str, Path]:
        """Return (relative_path_str, absolute_path) for the next audio blob."""
        with self._lock:
            self._turn_counter += 1
            n = self._turn_counter
        rel = f"audio/turn_{n:04d}.webm"
        return rel, self._dir / rel

    def record_turn_audio(self, audio_path: Path, blob: bytes) -> None:
        audio_path.write_bytes(blob)

    def open_turn(
        self,
        turn_id: str,
        ts: float,
        frame: int | None,
        transcript: str,
        stt_ms: float,
        audio_path: str,
        context_frame: Any,
    ) -> None:
        with self._lock:
            self._pending[turn_id] = {
                "turn_id": turn_id,
                "ts": ts,
                "frame": frame,
                "audio_path": audio_path,
                "transcript": transcript,
                "stt_ms": stt_ms,
                "context_frame": context_frame,
            }

    def close_turn(self, turn_id: str, response: str, llm_ms: float) -> None:
        with self._lock:
            entry = self._pending.pop(turn_id, None)
        if entry is None:
            logger.warning("SessionRecorder.close_turn: unknown turn_id %s", turn_id)
            return
        entry["response"] = response
        entry["llm_ms"] = llm_ms
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            self._interactions_file.write(line)
            self._interactions_file.flush()

    # ── Session lifecycle ──────────────────────────────────────────────────

    def write_meta(self, extra: dict[str, Any] | None = None) -> None:
        meta: dict[str, Any] = {
            "sessionId": self._dir.name,
            "startTs": self._start_ts,
            "gitSha": _git_sha(),
        }
        if extra:
            meta.update(extra)
        (self._dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    def close(self) -> None:
        with self._lock:
            try:
                self._telemetry_file.flush()
                self._telemetry_file.close()
            except Exception:
                pass
            try:
                self._telemetry_index.flush()
                self._telemetry_index.close()
            except Exception:
                pass
            try:
                self._interactions_file.flush()
                self._interactions_file.close()
            except Exception:
                pass


class _NoopRecorder:
    """Drop-in no-op used when F1_RECORD_DIR is not set."""

    def record_packet(self, *a, **kw) -> None:
        pass

    def flush_telemetry(self) -> None:
        pass

    def next_turn_audio_path(self) -> tuple[str, Path]:
        # Unused — callers guard with `is_active()`
        raise RuntimeError("NoopRecorder.next_turn_audio_path should not be called")

    def record_turn_audio(self, *a, **kw) -> None:
        pass

    def open_turn(self, *a, **kw) -> None:
        pass

    def close_turn(self, *a, **kw) -> None:
        pass

    def write_meta(self, *a, **kw) -> None:
        pass

    def close(self) -> None:
        pass


def build_recorder(session_dir: Path | None = None) -> SessionRecorder | _NoopRecorder:
    """Build a SessionRecorder from F1_RECORD_DIR, or return a no-op if unset."""
    record_dir = session_dir or (
        Path(os.environ["F1_RECORD_DIR"]) if os.environ.get("F1_RECORD_DIR") else None
    )
    if record_dir is None:
        return _NoopRecorder()
    return SessionRecorder(record_dir)


def is_active(recorder: SessionRecorder | _NoopRecorder) -> bool:
    return isinstance(recorder, SessionRecorder)
