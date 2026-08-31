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

# Enable session recording (writes to recordings/<timestamp>/)
python main.py --record
# Or specify a custom base directory
python main.py --record /path/to/dir

# MCP server standalone (stdio transport)
python -m src.mcp.server

# MCP server (HTTP transport)
python -m src.mcp.server --transport http --port 20915
```

## Testing & Utilities

```bash
# Run the full test suite (341 tests, ~6 s, no API keys, no game)
pytest -v
pytest --cov=src --cov-report=term-missing -v  # with coverage

# Run LLM agent evals (requires OPENAI_* keys; non-blocking, not part of CI)
make evals
python -m evals.runner --scenario radio_check        # single scenario
python -m evals.runner --judge --repeats 3           # with LLM-as-judge, 3 runs each
python -m evals.runner --out /tmp/my_eval.json       # custom output path

# Regenerate golden JSON fixtures after an intentional tool output change
python tests/fixtures/build_fixture.py --skip-parity --update-golden

# Text-based agent interaction (no voice)
python tests/text_agent.py

# Terminal-based live telemetry monitor (curses UI)
python tests/live_telemetry.py

# Test MCP telemetry tools via HTTP client
python tests/mcp_client.py

# Record live F1 UDP packets to a .bin file
python helpers/udp_sampler/record.py

# Replay captured packets (--loop for continuous replay)
python helpers/udp_sampler/replay.py --loop
```

A shipped capture file lives at `tests/fixtures/race_catalunya_2025.bin` (3.14 MB, used by the test suite). The full 70 MB source capture lives at `helpers/udp_sampler/capture_data/` and is only needed to regenerate the fixture from scratch (without `--skip-parity`).

## Setup

```bash
# Python dependencies (runtime + dev/test tools)
pip install -r requirements.txt -r requirements-dev.txt

# Node.js / Electron
npm install

# Install git hooks (runs ruff on every commit)
pre-commit install

# Rebuild C# wheel helper (Windows only, requires .NET 8)
dotnet publish -c Release -o helpers/wheel_detector/bin helpers/wheel_detector/WheelHelper.csproj
```

Copy `.env` with these keys:
- `DEEPGRAM_API_KEY` / `DEEPGRAM_MODEL` — Speech-to-Text
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` — LLM (OpenAI-compatible endpoint)
- `INWORLD_API_KEY` / `INWORLD_BASE_URL` / `INWORLD_MODEL` — Text-to-Speech

## Architecture

### Data Flow

```
F1 25 Game UDP (port 20777)
  → F1TelemetryCapture (src/live_data_engine/capture.py)
  → 16 packet decoders (src/udp_parser/packet_parsers/)
  → SessionStore + CarHistoryBuffers (src/live_data_engine/cache.py)
  → FastMCP tools (src/mcp/) — 6 tools: get_context_frame, get_leaderboard, get_lap_times, get_weather_forecast, get_strategy, get_recent_events
  → RaceEngineerAgent (src/voice_pipeline/agent.py) — LLM with MCP tool bindings
  → Flask REST API (src/web/web_transcribe_server.py)
      POST /transcribe — audio → STT → agent reply
      GET /tts — text → audio stream
  → Electron UI (src/ui/electron/) with global hotkey capture
```

### Key Components

**`src/udp_parser/`** — Binary packet decoders for F1 25 UDP protocol. `constants.py` contains all lookup tables (teams, drivers, tracks, button flags) aligned with the official spec in `docs/f1_telemetry_docs.md`. New packet types require a parser class + registration in `__init__.py`.

**`src/live_data_engine/`** — `F1TelemetryCapture` runs a UDP listener thread and dispatches to decoders. `SessionStore` and `CarHistoryBuffers` are in-memory ringbuffers (configurable via `F1_BUFFER_*` env vars). All data is ephemeral — no database. `fixture_replay.py` provides `replay_fixture_into(capture, bin_path, frame)` — the shared decode loop used by both the test suite and the MCP server's fixture mode.

**`src/mcp/`** — FastMCP service. `functions/` contains the actual telemetry query logic (one file per tool); `tools.py` registers them as MCP tools; `server.py` is the entrypoint. Supports stdio (local agent) or HTTP transport. Two env-var hooks in `server.py` / `tools.py`:
- `F1_MCP_FIXTURE` + `F1_MCP_FIXTURE_FRAME` — skip UDP, seed from a `.bin` fixture file instead (used by evals)
- `F1_MCP_TOOL_LOG` — append `{"tool": name, "ts": ...}` JSON lines to a file on every tool call (used by evals to score tool selection)

**`src/voice_pipeline/`** — `RaceEngineerAgent` (Microsoft Agent Framework) orchestrates STT → LLM → TTS. The `get_context_frame` MCP tool is automatically included in every LLM call to provide current telemetry. STT uses Deepgram Nova 3; TTS uses Inworld AI (48kHz mono PCM L16). `RaceEngineerAgent(mcp_env=...)` accepts an optional env dict passed through to `MCPStdioTool` — required for evals because `mcp`'s `stdio_client` uses `get_default_environment()` (not the full parent env) when spawning the subprocess.

**`src/web/web_transcribe_server.py`** — Flask app that initializes the agent and exposes `/transcribe` and `/tts`. The async agent event loop runs in a background thread.

**`src/ui/electron/main.js`** — Electron shell loading `http://127.0.0.1:8080`. Global hotkeys are captured via `uiohook-napi`; steering wheel buttons come from a spawned `WheelHelper.exe` subprocess (C#/.NET 8, communicates via stdout).

**`src/ui/web_static/`** — Vanilla JS frontend using Web Audio API for recording.

### MCP Tool Context Frame

`get_context_frame` is the primary tool — it assembles a rich snapshot of current session state, car telemetry, lap times, position changes, and events into a single context object for the LLM. It is injected automatically (not on demand) before each agent turn. Fuel lap delta (`lapsRemaining`, `deltaLaps`) is always included; the `status` field is `"critical"` only when the game signals a hard low-fuel warning.

### Test suite (`tests/`)

341 tests, ~6 s, no API keys, no game. See `tests/README.md` for full details.

- **`tests/fixtures/race_catalunya_2025.bin`** — 3.14 MB committed fixture slice, validated against a 70 MB source via a parity gate at every race marker. Regenerate with `build_fixture.py`.
- **`tests/helpers.py`** — `load_capture_to(frame)` loads the fixture in-process through the production decode path. `mask()` strips wall-clock fields before golden comparison.
- **`tests/deterministic/test_tools_golden.py`** — 12 exact golden comparisons (4 tools × 3 scenarios). When an intentional output change breaks goldens, regenerate with `--update-golden`.
- **`tests/deterministic/test_tools_invariants.py`** — 30 semantic invariants across all 6 tools.
- **`tests/integration/`** — MCP tool registration wiring, Flask endpoint smoke tests.

### Eval harness (`evals/`)

On-demand LLM quality gate — **not** part of the normal `pytest` run. Requires real `OPENAI_*` keys. See `docs/evals.md` for full details.

- **`evals/scenarios.py`** — 12 scenarios, each pinned to a fixture frame. Fields: `driver` (spoken question), `expect_tools`, `must_include`, `must_not_include`, `rubric`.
- **`evals/scorers.py`** — 5 programmatic scorers: `brevity`, `format_check`, `no_forbidden_phrase`, `grounding`, `tool_selection`. Optional `judge` scorer uses the LLM to rate against `rubric`.
- **`evals/runner.py`** — CLI that seeds the MCP subprocess via `F1_MCP_FIXTURE*` env vars, drives `RaceEngineerAgent.reply_async`, reads tool logs, and runs scorers. Each scenario spawns and tears down its own agent + MCP subprocess.
- **`.github/workflows/evals.yml`** — manual dispatch (`workflow_dispatch`) + weekly schedule. Never triggers on push/PR. Uploads the JSON report as a build artifact.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `F1_UDP_IP` | `0.0.0.0` | UDP bind address |
| `F1_UDP_PORT` | `20777` | UDP listen port |
| `F1_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `F1_MCP_HOST` | `127.0.0.1` | MCP HTTP host |
| `F1_MCP_PORT` | `20915` | MCP HTTP port |
| `F1_BUFFER_CAR_TELEMETRY` | `120` | Ringbuffer sizes per data type |
| `F1_MCP_FIXTURE` | — | Path to a `.bin` fixture file; skips UDP and seeds capture from file instead |
| `F1_MCP_FIXTURE_FRAME` | — | Frame index to stop replay at (used with `F1_MCP_FIXTURE`) |
| `F1_MCP_TOOL_LOG` | — | Path to append tool-call JSON lines to on every MCP tool invocation |
| `F1_RECORD_DIR` | — | Path to the active recording directory; set automatically by `--record` flag. When set, enables the session recorder in both the Flask process and the MCP subprocess. A full race recording is typically 10–70 MB (dominated by raw telemetry). |
