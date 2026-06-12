"""Unit tests for src/observability/session_recorder.py"""

import json
import struct
from pathlib import Path

import pytest

from src.observability.session_recorder import (
    SessionRecorder,
    _NoopRecorder,
    build_recorder,
    is_active,
)


@pytest.fixture()
def rec(tmp_path):
    r = SessionRecorder(tmp_path / "session")
    yield r
    r.close()


# ── build_recorder / is_active ─────────────────────────────────────────────


def test_build_recorder_noop_when_no_env(monkeypatch):
    monkeypatch.delenv("F1_RECORD_DIR", raising=False)
    r = build_recorder()
    assert isinstance(r, _NoopRecorder)
    assert not is_active(r)


def test_build_recorder_active_with_env(tmp_path, monkeypatch):
    session_dir = tmp_path / "rec"
    monkeypatch.setenv("F1_RECORD_DIR", str(session_dir))
    r = build_recorder()
    assert is_active(r)
    r.close()


def test_build_recorder_explicit_dir(tmp_path):
    r = build_recorder(session_dir=tmp_path / "explicit")
    assert is_active(r)
    r.close()


# ── Noop recorder ─────────────────────────────────────────────────────────


def test_noop_recorder_all_methods_safe():
    r = _NoopRecorder()
    r.record_packet(b"\x00" * 8, 1.0, 1, 0)
    r.flush_telemetry()
    r.record_turn_audio(Path("/dev/null"), b"")
    r.open_turn("id", 1.0, None, "hi", 100.0, "audio/turn_0001.webm", {})
    r.close_turn("id", "response", 200.0)
    r.write_meta()
    r.close()


# ── Telemetry recording ────────────────────────────────────────────────────


def test_record_packet_writes_length_prefixed_bin(rec, tmp_path):
    payload = b"\xab\xcd" * 32
    rec.record_packet(payload, 1000.0, 42, 6)
    rec.close()

    session_dir = tmp_path / "session"
    bin_path = session_dir / "telemetry.bin"
    assert bin_path.exists()
    data = bin_path.read_bytes()
    length = struct.unpack_from("<H", data, 0)[0]
    assert length == len(payload)
    assert data[2 : 2 + length] == payload


def test_telemetry_bin_reloadable_by_fixture_replay(rec, tmp_path):
    """telemetry.bin written by recorder must be readable by replay_fixture_into."""
    # Simulate what the packet sink would write
    session_dir = tmp_path / "session"
    for i in range(5):
        fake_packet = bytes(range(i, i + 48))  # minimal dummy
        rec.record_packet(fake_packet, 1000.0 + i, i, 0)
    rec.close()

    bin_path = session_dir / "telemetry.bin"
    assert bin_path.stat().st_size > 0

    # The file can be opened and iterated by the same reader fixture_replay uses
    from src.live_data_engine.fixture_replay import _read_packets

    packets = _read_packets(bin_path)
    assert len(packets) == 5


def test_telemetry_index_written(rec, tmp_path):
    rec.record_packet(b"\x00" * 10, 1234.5, 99, 3)
    rec.flush_telemetry()
    rec.close()

    lines = (tmp_path / "session" / "telemetry_index.jsonl").read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["frame"] == 99
    assert row["packetId"] == 3
    assert abs(row["ts"] - 1234.5) < 0.01


# ── Turn recording ─────────────────────────────────────────────────────────


def test_open_close_turn_writes_interactions_jsonl(rec, tmp_path):
    rec.open_turn(
        turn_id="abc",
        ts=2000.0,
        frame=777,
        transcript="whats the gap",
        stt_ms=150.0,
        audio_path="audio/turn_0001.webm",
        context_frame={"meta": {"frame": 777}},
    )
    rec.close_turn("abc", "Gap is 2 seconds.", 900.0)
    rec.close()

    lines = (tmp_path / "session" / "interactions.jsonl").read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["turn_id"] == "abc"
    assert row["transcript"] == "whats the gap"
    assert row["response"] == "Gap is 2 seconds."
    assert row["frame"] == 777
    assert row["stt_ms"] == 150.0
    assert row["llm_ms"] == 900.0
    assert row["audio_path"] == "audio/turn_0001.webm"


def test_multiple_turns_sequential(rec, tmp_path):
    for i in range(3):
        tid = f"turn-{i}"
        rec.open_turn(tid, 1000.0 + i, i, f"question {i}", 100.0, f"audio/turn_{i:04d}.webm", {})
        rec.close_turn(tid, f"answer {i}", 200.0)
    rec.close()

    lines = (tmp_path / "session" / "interactions.jsonl").read_text().splitlines()
    assert len(lines) == 3
    for i, line in enumerate(lines):
        row = json.loads(line)
        assert row["turn_id"] == f"turn-{i}"
        assert row["transcript"] == f"question {i}"


def test_close_unknown_turn_id_is_silent(rec):
    rec.close_turn("nonexistent", "reply", 100.0)  # must not raise


def test_audio_blob_saved(rec, tmp_path):
    audio_rel, audio_abs = rec.next_turn_audio_path()
    rec.record_turn_audio(audio_abs, b"\xff\xfb\x90" * 100)
    rec.close()

    assert audio_abs.exists()
    assert audio_abs.read_bytes() == b"\xff\xfb\x90" * 100
    assert audio_rel.startswith("audio/")


def test_next_turn_audio_path_increments(rec):
    paths = [rec.next_turn_audio_path()[0] for _ in range(3)]
    assert paths == ["audio/turn_0001.webm", "audio/turn_0002.webm", "audio/turn_0003.webm"]


# ── Meta file ─────────────────────────────────────────────────────────────


def test_write_meta_creates_json(rec, tmp_path):
    rec.write_meta({"track": "Catalunya"})
    meta = json.loads((tmp_path / "session" / "meta.json").read_text())
    assert meta["sessionId"] == "session"
    assert meta["track"] == "Catalunya"
    assert "startTs" in meta
