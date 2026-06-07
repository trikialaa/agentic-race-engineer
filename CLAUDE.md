# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**f1_radio** is a Virtual F1 Race Engineer that pairs Codemasters F1 25 UDP telemetry data with an AI-powered voice assistant. The user speaks to an AI "Bono" (race engineer persona), which queries live telemetry via MCP tools and responds with tactical guidance.

## Running the Project

```bash
# Full stack: Flask server + Electron UI
python main.py

# Flask API only (no Electron window)
python main.py --skip-electron

# Custom host/port
python main.py --host 0.0.0.0 --port 8000

# MCP server standalone (stdio transport)
python -m src.mcp.server

# MCP server (HTTP transport)
python -m src.mcp.server --transport http --port 20915
```

## Testing & Utilities

```bash
# Test MCP telemetry tools via HTTP client
python tests/mcp_client.py

# Text-based agent interaction (no voice)
python tests/text_agent.py

# Terminal-based live telemetry monitor (curses UI)
python tests/live_telemetry.py

# Record live F1 UDP packets to a .bin file
python helpers/udp_sampler/record.py

# Replay captured packets (--loop for continuous replay)
python helpers/udp_sampler/replay.py --loop
```

A shipped capture file lives at `helpers/udp_sampler/capture_data/` for development without a running game.

## Setup

```bash
# Python dependencies
pip install -r requirements.txt

# Node.js / Electron
npm install

# Rebuild C# wheel helper (Windows only, requires .NET 8)
dotnet publish -c Release -o helpers/wheel_detector/bin helpers/wheel_detector/WheelHelper.csproj
```

Copy `.env` with these keys:
- `DEEPGRAM_API_KEY` / `DEEPGRAM_MODEL` — Speech-to-Text
- `BASETEN_API_KEY` / `BASETEN_BASE_URL` / `BASETEN_MODEL` — LLM (OpenAI-compatible endpoint)
- `INWORLD_API_KEY` / `INWORLD_BASE_URL` / `INWORLD_MODEL` — Text-to-Speech

## Architecture

### Data Flow

```
F1 25 Game UDP (port 20777)
  → F1TelemetryCapture (src/live_data_engine/capture.py)
  → 16 packet decoders (src/udp_parser/packet_parsers/)
  → SessionStore + CarHistoryBuffers (src/live_data_engine/cache.py)
  → FastMCP tools (src/mcp/) — 4 tools: get_context_frame, get_leaderboard, get_lap_times, get_weather_forecast
  → RaceEngineerAgent (src/voice_pipeline/agent.py) — LLM with MCP tool bindings
  → Flask REST API (src/web/web_transcribe_server.py)
      POST /transcribe — audio → STT → agent reply
      GET /tts — text → audio stream
  → Electron UI (src/ui/electron/) with global hotkey capture
```

### Key Components

**`src/udp_parser/`** — Binary packet decoders for F1 25 UDP protocol. `constants.py` contains all lookup tables (teams, drivers, tracks, button flags) aligned with the official spec in `docs/f1_telemetry_docs.md`. New packet types require a parser class + registration in `__init__.py`.

**`src/live_data_engine/`** — `F1TelemetryCapture` runs a UDP listener thread and dispatches to decoders. `SessionStore` and `CarHistoryBuffers` are in-memory ringbuffers (configurable via `F1_BUFFER_*` env vars). All data is ephemeral — no database.

**`src/mcp/`** — FastMCP service. `functions.py` contains the actual telemetry query logic; `tools.py` registers them as MCP tools; `server.py` is the entrypoint. Supports stdio (local agent) or HTTP transport.

**`src/voice_pipeline/`** — `RaceEngineerAgent` (Microsoft Agent Framework) orchestrates STT → LLM → TTS. The `get_context_frame` MCP tool is automatically included in every LLM call to provide current telemetry. STT uses Deepgram Nova 3; TTS uses Inworld AI (48kHz mono PCM L16).

**`src/web/web_transcribe_server.py`** — Flask app that initializes the agent and exposes `/transcribe` and `/tts`. The async agent event loop runs in a background thread.

**`src/ui/electron/main.js`** — Electron shell loading `http://127.0.0.1:8080`. Global hotkeys are captured via `uiohook-napi`; steering wheel buttons come from a spawned `WheelHelper.exe` subprocess (C#/.NET 8, communicates via stdout).

**`src/ui/web_static/`** — Vanilla JS frontend using Web Audio API for recording. Displays STT/LLM/TTS latency separately.

### MCP Tool Context Frame

`get_context_frame` is the primary tool — it assembles a rich snapshot of current session state, car telemetry, lap times, position changes, and events into a single context object for the LLM. It is injected automatically (not on demand) before each agent turn.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `F1_UDP_IP` | `0.0.0.0` | UDP bind address |
| `F1_UDP_PORT` | `20777` | UDP listen port |
| `F1_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `F1_MCP_HOST` | `127.0.0.1` | MCP HTTP host |
| `F1_MCP_PORT` | `20915` | MCP HTTP port |
| `F1_BUFFER_CAR_TELEMETRY` | `120` | Ringbuffer sizes per data type |
