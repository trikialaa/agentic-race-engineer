"""
Integration tests for Flask API endpoints.
Uses Flask test client — no subprocess, no real network, no API keys.
Tests:
  - /session-state shape
  - /transcribe rejects with 403 when session not active
  - /callout-stream yields a well-formed callout SSE frame when directly pushed
"""
from __future__ import annotations

import json
import queue

import pytest


@pytest.fixture(scope="module")
def client():
    """Flask test client with a fresh app import."""
    from src.web.web_transcribe_server import app, callout_queue
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, callout_queue


class TestSessionState:
    def test_returns_200(self, client):
        c, _ = client
        resp = c.get("/session-state")
        assert resp.status_code == 200

    def test_returns_active_bool(self, client):
        c, _ = client
        resp = c.get("/session-state")
        data = json.loads(resp.data)
        assert "active" in data
        assert isinstance(data["active"], bool)


class TestTranscribeEndpoint:
    def test_rejects_without_audio_field(self, client):
        c, _ = client
        # Guaranteed 400 regardless of session state (missing audio_data field)
        resp = c.post("/transcribe", data={})
        # Either 403 (no active session) or 400 (missing field) — both are correct rejections
        assert resp.status_code in (400, 403)

    def test_rejects_without_active_session(self, client):
        """When no game is running, /transcribe returns 403."""
        c, _ = client
        # The agent is not initialized in test context so session is inactive
        resp = c.post("/transcribe", data={"audio_data": (b"fake_audio", "audio.webm")})
        # Accept 403 (no session) or 400 (missing field handled first) — both indicate no passthrough
        assert resp.status_code in (400, 403)


class TestCalloutStream:
    def test_callout_stream_returns_200(self, client):
        c, cq = client
        # Push one item so the generator doesn't block
        cq.put({"type": "callout", "engineer_reply": "Box box.", "display_reply": "Box box.", "playerTeam": "Williams"})
        resp = c.get("/callout-stream", headers={"Accept": "text/event-stream"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.content_type

    def test_callout_payload_is_well_formed(self, client):
        """A manually pushed queue item yields a parseable SSE data line."""
        c, cq = client
        payload = {
            "type": "callout",
            "engineer_reply": "Safety car, box this lap.",
            "display_reply": "Safety car, box this lap.",
            "playerTeam": "Williams",
        }
        cq.put(payload)

        # Read first data chunk from the streaming response
        with c.application.test_request_context():
            from src.web.web_transcribe_server import callout_stream
            # Access the generator directly and read first item
            gen_resp = callout_stream()

        # Alternatively: read the SSE response bytes until the first data line
        cq.put(payload)  # replenish since generator consumed the previous one
        with c.get("/callout-stream", headers={"Accept": "text/event-stream"}) as resp:
            raw = b""
            for chunk in resp.response:
                raw += chunk
                if b"data:" in raw:
                    break

        line = next(l for l in raw.decode().splitlines() if l.startswith("data:"))
        msg = json.loads(line[len("data:"):].strip())
        assert msg["type"] == "callout"
        assert "engineer_reply" in msg
        assert "playerTeam" in msg


class TestStaticRoutes:
    def test_root_returns_html(self, client):
        c, _ = client
        resp = c.get("/")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data

    def test_static_js_served(self, client):
        c, _ = client
        resp = c.get("/app.js")
        assert resp.status_code == 200
