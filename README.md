# f1_radaio
Virtual F1 race engineer that pairs Codemasters UDP telemetry with a FastMCP surface, a Flask-based REST API, and an Electron UI front end.

## Layout

- `docs/`
  - `f1_telemetry_docs.md` — the definitive telemetry appendix for the live parsers; all team names, drivers, game modes, and button flags in `src/udp_parser/constants.py` are aligned with these tables.
- `helpers/`
  - `udp_sampler/`
    - `capture_data/` (contains the shipped `f1_25_capture_20260412_151325.bin` and any future recordings).
    - `record.py` — simple UDP recorder that drops packets into the `capture_data` folder.
    - `replay.py` — replays a capture (defaults to the shipped `f1_25_capture…` file and can loop indefinitely with `--loop`).
  - `wheel_detector/`
    - `WheelHelper.csproj` plus the published `bin/Release/net8.0/WheelHelper.exe` that the Electron shell uses for wheel events.
- `src/`
  - `udp_parser/` — packet decoders plus the shared `constants.py` (teams, game modes, button flags, tracks, etc.).
  - `live_data_engine/` — `capture.py` with the UDP thread + `cache.py` helpers (`CarHistoryBuffers`, `SessionStore`).
  - `mcp/` — FastMCP wiring: the callable functions, the registry helper, and the server entry point.
  - `voice_pipeline/` — the Autogen/OpenAI-powered race engineer (agent, STT, TTS, and workbench helpers).
  - `session_manager/` — Flask transcription/agent server (`web_transcribe_server.py`).
  - `ui/`
    - `electron/` — the Electron shell, preload script, and wheel-hotkey logic.
    - `web_static/` — React-inspired static assets consumed by the Electron window.
- `tests/`
  - `mcp_client.py` — FastMCP client runner that exercises every telemetry tool.
  - `live_telemetry.py` — curses-based UDP monitor that lives under `src` parsers.
- `main.py` — single entry point that waits for the Flask agent then launches Electron; closing the window tears down both sides and prompts to restart.

## Running the stack

1. Install the Python dependencies you need (`fastmcp`, `flask`, `werkzeug`, etc.).
2. Build the wheel helper so the Electron shell can read wheel buttons: `dotnet publish -c Release -o helpers/wheel_detector/bin helpers/wheel_detector/WheelHelper.csproj`.
3. From the repo root run `npm install` (or `npm ci` if you want to restore the lockfile exactly) so Electron and `uiohook-napi` are rebuilt for your OS; from WSL/Linux you must reinstall so the native `.node` module matches Linux (the “invalid ELF header” error means a Windows build was loaded).
4. Launch everything with `python main.py`. The Flask server starts first, then Electron opens at `http://127.0.0.1:8080`; closing the window stops both services and you can restart when prompted.

If you need just the Flask API for testing, run `python main.py --skip-electron`.

## Testing & utilities

- `helpers/udp_sampler/record.py` and `helpers/udp_sampler/replay.py` let you capture packet dumps and replay the supplied `helpers/udp_sampler/capture_data/f1_25_capture_20260412_151325.bin` (looping via `--loop` is also supported).
- `tests/mcp_client.py` spins up `src/mcp/server.py` via FastMCP and exercises every registered telemetry tool.
- `tests/live_telemetry.py` is the terminal board; it now imports the shared `src/udp_parser` decoders/constants and runs independently of the old `ui/live_telemetry.py`.

## F1 telemetry reference

- `docs/f1_telemetry_docs.md` mirrors the official F1 25 UDP appendix.
- `src/udp_parser/constants.py` is derived directly from that document; the `TEAM_NAMES`, `BUTTON_FLAGS`, `GAME_MODES`, and related tables have been verified against the reference so team lists, driver names, game modes, and button flag meanings are accurate.
