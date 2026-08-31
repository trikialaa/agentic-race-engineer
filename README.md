# Agentic F1 Race Engineer

**Virtual F1 Race Engineer** — pairs Codemasters F1 25 UDP telemetry with an AI-powered voice
assistant that responds to your questions in real time, exactly like a real race engineer.

[![CI](https://github.com/trikialaa/agentic-race-engineer/actions/workflows/tests.yml/badge.svg)](https://github.com/trikialaa/agentic-race-engineer/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Unofficial project.** Not affiliated with Formula 1, EA, or Codemasters. See [DISCLAIMER.md](DISCLAIMER.md).

---

## Video Demo

[![Demo video](https://img.youtube.com/vi/BVU3ri6X4aI/maxresdefault.jpg)](https://youtu.be/BVU3ri6X4aI)

Sample exchange:
> **You:** "Bono, what's my tyre deg looking like?"
> **Bono:** "Front-left at thirty-two percent wear, rear-left twenty-eight. You're good for another eight laps on the mediums."

---

## How it works

```
F1 25 Game (UDP :20777)
        │  ~60 Hz packet stream
        ▼
F1TelemetryCapture          16 typed packet decoders
(src/live_data_engine/)  ──────────────────────────▶  SessionStore + CarHistoryBuffers
                                                        (in-memory ringbuffers)
                                                               │
                                                               ▼
                                                     7 FastMCP tools
                                                     (src/mcp/functions/)
                                                               │
                                              ┌────────────────┴──────────────────┐
                                              │                                   │
                                              ▼                                   ▼
                                    RaceEngineerAgent                    CalloutMonitor
                                    (src/voice_pipeline/)           (autonomous proactive
                                    STT → LLM + MCP → TTS            race event alerts)
                                    Radio FX (DSP)
                                              │
                                              ▼
                                     Flask REST API
                                   (src/web/)
                                   POST /transcribe
                                   GET  /tts
                                   GET  /callout-stream
                                              │
                                              ▼
                                      Electron UI
                                  (src/ui/electron/)
                              global hotkey · steering wheel
```

The game streams UDP packets at ~60 Hz. Each packet is decoded by a typed parser and merged
into in-memory ringbuffers. On every voice interaction, `get_context_frame` is automatically
injected into the LLM context — position, tyres, fuel, gaps, weather, events — so the model
always has live race state without the user needing to ask for it.

---

## Features

**Voice pipeline**
- Push-to-talk via keyboard hotkey or steering wheel button (C#/.NET 8 helper)
- Deepgram Nova 3 STT with sub-200 ms first-token latency
- OpenAI-compatible LLM with live telemetry via 7 MCP tools
- Inworld AI TTS at 48 kHz / 16-bit mono PCM
- Radio FX DSP (biquad band-limit + mic saturation + static hiss) for authentic team-radio sound

**Proactive callouts**
The `CalloutMonitor` fires unsolicited engineer messages on race events (safety car, collisions,
penalties, overtakes, DRS zones, fastest laps) using per-event cooldowns and a global rate
limit to avoid spamming the driver.

**Session recording**
When `--record` is passed, a time-aligned trace is written to `recordings/<timestamp>/`:
raw telemetry (`.bin`), per-packet index (`.jsonl`), mic audio blobs, full interaction
transcripts, and MCP tool call logs. Used to build regression fixtures from real races.

---

## MCP Tools

| Tool | Purpose |
|---|---|
| `get_context_frame` | Rich snapshot: position, gaps, tyres, fuel, damage, DRS, session phase — auto-injected before every LLM turn |
| `get_leaderboard` | Full 20-car field with gaps, tyre compounds, age, pit stop counts, and penalties |
| `get_lap_times` | Per-car lap and sector times with best/recent splits for pace analysis |
| `get_weather_forecast` | Current track/air conditions and a time-series rain forecast |
| `get_strategy` | Pit window, available tyre sets with wear and pace delta, estimated rejoin position |
| `get_recent_events` | Race events (safety car, penalties, overtakes, fastest lap) with severity and timestamps |
| `get_race_report` | End-of-session summary: finishing positions, fastest laps, tyre lifecycle, stint history |

Each tool carries a detailed description that steers the LLM to call the narrowest tool for
each query and avoid redundant calls when `get_context_frame` already has the answer.

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node.js 18+ (for the Electron UI)
- F1 25 — Settings → Telemetry → UDP Output: **On**, Port: **20777**

### Install

```bash
git clone https://github.com/trikialaa/agentic-race-engineer.git && cd agentic-race-engineer

pip install -r requirements.txt -r requirements-dev.txt
npm ci

cp .env.example .env
# Fill in: DEEPGRAM_API_KEY, OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL,
#          INWORLD_API_KEY / INWORLD_BASE_URL / INWORLD_MODEL
```

### Run

```bash
# Full stack — Flask API + Electron overlay window
python main.py

# Headless — Flask API only, no Electron, no game required
python main.py --skip-electron

# With UDP packet replay instead of a live game
python helpers/udp_sampler/replay.py --loop &
python main.py --skip-electron

# Enable session recording
python main.py --record
```

Press and hold the configured hotkey (or a steering wheel button) and speak. Release to submit.

---

## Development

```bash
make lint       # ruff check + format check
make typecheck  # mypy (src/mcp/functions, src/udp_parser)
make test       # pytest with coverage (341 tests, ~6 s, no API keys, no game)

pre-commit install   # install git hooks (ruff on every commit)
```

### Running the test suite in Docker

```bash
docker build --target test -t f1-test .
docker run --rm f1-test
```

### Evals (LLM quality gate)

The eval harness is separate from the unit/integration test suite and requires real API keys.
It drives `RaceEngineerAgent` against 12 pinned fixture scenarios and scores responses with
5 programmatic scorers (`brevity`, `format_check`, `no_forbidden_phrase`, `grounding`,
`tool_selection`) plus an optional LLM-as-judge.

```bash
make evals                                           # all 12 scenarios
python -m evals.runner --scenario radio_check        # single scenario
python -m evals.runner --judge --repeats 3           # with LLM judge, 3 runs each
```

See [docs/evals.md](docs/evals.md) for scenario definitions, scorer design, and CI integration.

---

## Cost & latency

Currently running `gpt-5.4-nano` (OpenAI) for the agent LLM, Deepgram `nova-3` for STT
(batch, not streaming), and Inworld `tts-2` for voice output.

**Latency**, measured from 57 real agent runs in `evals/results/` (LLM + any MCP tool call,
context frame already injected):

| | Time |
|---|---|
| Median | 1.36 s |
| Mean | 1.46 s |
| P90 | 2.3 s |

Add STT and TTS on top of this for true mic-to-speaker latency.

**Cost per 5-lap session**, estimated rather than metered. Assumes 5 radio exchanges per
lap, 25 total, 20 of them spoken (STT). Sized from the real system prompt (~2.5k tokens),
a real `get_context_frame` payload (~265 tokens), and the average reply length from eval
runs (38.8 characters):

| Component | Rate | Est. per session |
|---|---|---|
| LLM (`gpt-5.4-nano`) | $0.20 / $1.25 per 1M in/out tokens | ~$0.015 |
| STT (Deepgram `nova-3`, batch) | $0.0043 / min | ~$0.004 |
| TTS (Inworld `tts-2`) | $35 / 1M characters | ~$0.034 |
| **Total** | | **~$0.05** |

TTS is the biggest line item at Inworld's current rate. The terse reply style the `brevity`
scorer enforces is a real cost lever, not just UX. The system prompt is static per turn and
not currently cached, so prompt caching would cut the LLM line further. `evals/compare.py`
can A/B a cheaper backend (Groq, Cerebras) against quality, not just cost.

---

## Engineering highlights

- 341 tests, ~6 s, no game, no API keys, no mocks. Golden-snapshot and invariant tests
  for all 7 MCP tools, run against a fixture parity-gated against a real 70 MB race capture.
- A separate eval harness (`evals/`) scores the agent itself: 12 pinned scenarios, 5
  programmatic scorers, an optional LLM-as-judge, and `evals/compare.py` for A/B testing
  model backends head to head.
- 16 UDP packet decoders, fully typed and mypy-checked in CI across Python 3.11 and 3.12.
- `get_context_frame` is injected into every LLM turn unconditionally instead of fetched
  on demand, so voice replies land in under a second. See [Design notes](#design-notes).
- `CalloutMonitor` runs independently of the request/response loop, firing rate-limited
  proactive radio calls on race events: safety car, position loss, penalties, fastest laps.

---

## Design notes

**Why MCP as the tool boundary?**
[Model Context Protocol](https://modelcontextprotocol.io) gives the LLM a clean, typed
interface to query telemetry on demand and decouples the agent from the data layer entirely.
New tools can be added or the LLM swapped without touching parsers or the Flask server.
The MCP server supports both `stdio` (local agent subprocess) and `http` transports.

**Why in-memory ringbuffers, not a database?**
F1 telemetry is ephemeral by nature — a lap time from three laps ago has no tactical relevance.
Ringbuffers keep write amplification at zero while tools always see the freshest data. No schema,
no migrations, no persistence overhead. Buffer sizes are tunable via `F1_BUFFER_*` env vars.

**Why is `get_context_frame` auto-injected?**
Requiring the agent to request telemetry before every reply adds a full LLM round-trip of
latency. Injecting the context frame unconditionally keeps end-to-end response time under 1 s
while ensuring the model never answers from stale in-weights knowledge about the race.

**Why a parity-gated fixture for tests?**
The test suite feeds a 3.14 MB downsampled slice of a real Catalunya race to the production
decode path in-process — no socket, no API keys, ~5 s. Before the slice was committed it was
validated against the full 70 MB source at every race marker, asserting masked-equal output
across all tools. The fixture is a *behaviorally faithful* proxy, not a lossy approximation.
See [tests/README.md](tests/README.md).

---

## Project layout

```
src/
  udp_parser/           # Binary packet decoders for all F1 25 packet types + constants
  live_data_engine/     # UDP listener thread, SessionStore, CarHistoryBuffers, fixture replay
  mcp/                  # FastMCP: tools.py (registration), functions/ (one file per tool)
  voice_pipeline/       # RaceEngineerAgent, STT, TTS, radio FX DSP, CalloutMonitor
  web/                  # Flask REST API (/transcribe, /tts, /callout-stream)
  observability/        # Session recorder (telemetry + audio + interaction traces)
  ui/
    electron/           # Electron shell, global hotkey capture, WheelHelper subprocess
    web_static/         # Vanilla JS frontend — Web Audio API, latency display

helpers/
  udp_sampler/          # record.py, replay.py, and the full 70 MB source capture
  wheel_detector/       # C#/.NET 8 WheelHelper.exe — steering wheel button detection

tests/
  fixtures/             # 3.14 MB race fixture, markers.json, golden JSON snapshots
  unit/                 # Pure function tests (parsers, callouts, config, recorder, query)
  deterministic/        # Golden-snapshot + invariant tests for all 7 MCP tools
  integration/          # MCP registration, Flask endpoints, SSE callout stream

evals/
  scenarios.py          # 12 scenarios pinned to fixture frames, each with expected tools + rubric
  scorers.py            # 5 programmatic scorers + optional LLM-as-judge
  runner.py             # CLI: seeds MCP subprocess, drives agent, reads tool logs, runs scorers

docs/
  f1_telemetry_docs.md  # F1 25 UDP specification (reference)
  evals.md              # Eval harness design, scorer definitions, CI integration
```

---

## Legal

This project is unofficial and not affiliated with Formula 1, the FIA, EA Sports, or
Codemasters. "F1", "Formula 1", team names, and driver names are trademarks of their respective
owners. For personal, educational, non-commercial use only. See [DISCLAIMER.md](DISCLAIMER.md).
