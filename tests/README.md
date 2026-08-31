# Test suite

341 tests, ~6 s, no API keys, no game, no subprocess.

## Structure

```
tests/
  conftest.py                  # autouse fixtures: lap-times state reset, buffer env pins
  helpers.py                   # shared: load_capture_to(), mask(), load_golden()
  fixtures/
    race_catalunya_2025.bin    # 3.14 MB committed fixture slice
    markers.json               # frame indices: start, green_steady, mid_strategy, finish
    golden/                    # 12 committed JSON files: {tool}__{scenario}.json
    build_fixture.py           # dev-time only — rebuilds the fixture from the 70 MB source
  unit/
    test_shared_helpers.py     # pure helper functions (_round, _normalize_tyre_compound, etc.)
    test_config_backcompat.py  # config migration (proactiveEvents → engineerCallouts)
    test_callout_decisions.py  # CalloutMonitor severity / cooldown / PTT logic (LLM stubbed)
    test_parsers.py            # packet parsers on real bytes from the fixture
  deterministic/
    test_tools_golden.py       # 12 exact golden comparisons (4 tools × 3 scenarios)
    test_tools_invariants.py   # 30 semantic invariants across all 6 tools
  integration/
    test_tools_registration.py # FastMCP tool registration wiring
    test_flask_endpoints.py    # Flask /session-state, /transcribe, /callout-stream, static
```

## The fixture and the parity gate

The test suite's linchpin is `tests/fixtures/race_catalunya_2025.bin` — a 3.14 MB downsampled
slice of a 70 MB Catalunya 2025 race capture.

**Why a committed binary?**
Tests need deterministic, key-free inputs. The full capture is too large to commit (70 MB).
But a naive trim would miss critical low-frequency packets (Participants fires only 89 times in
the full file; missing even one corrupts team/driver lookups for the rest of the race).

**Downsampling strategy**
`build_fixture.py` applies different retention policies per packet type:

| Category | Types (packet IDs) | Policy |
|---|---|---|
| Dropped entirely | Motion (0), Car Setups (5) | No tool reads these |
| Keep all | Events (3), Participants (4), Session (1), Final Classification (8), Lap Positions (14), others | Low frequency or safety-critical |
| Session History | Session History (11) | Keep every 15th |
| Snapshots | Lap Data (2), Car Status (6), Car Telemetry (7), Car Damage (10), Tyre Sets (12), Motion Ex (13), Time Trial (15) | Keep every 30th + always keep the last packet of each type before each marker |

**The parity gate** is what makes this safe: after downsampling, `build_fixture.py` replays
both the full source and the slim fixture in-process, calls the four pure-read tools
(`get_context_frame`, `get_leaderboard`, `get_weather_forecast`, `get_strategy`) at every
marker frame, strips wall-clock fields, and asserts the outputs are identical. If any type
breaks parity (e.g. session_history was too sparse), the script fails loudly with a diff.

**Why are `get_lap_times` and `get_recent_events` excluded from golden/parity tests?**
Two determinism hazards prevent them from being parity-compared:

- `get_lap_times` depends on `_LAP_TIMES_STATE`, a module-level accumulator that folds in
  per-car history packets as they arrive. The downsampled fixture keeps every 15th
  session_history packet, so the accumulator sees a different number of packets than the full
  replay — the per-car history counts differ. Both are *valid* (neither is wrong), but they
  aren't equal. These tools are covered by structural invariants instead.

- `get_recent_events` deduplicates events by wall clock (`_event_dedupe_ttl_s = 2.0`) at
  ingest time. In the in-process replay, packets that arrived seconds apart in real time arrive
  microseconds apart — some events that survived deduplication in real-time playback are
  collapsed in the fast in-process replay. Again, structural invariants cover the correctness
  properties that matter.

## In-process capture loader (`helpers.load_capture_to`)

Tests don't start a UDP socket or spawn threads. `load_capture_to(frame=N)` reads the binary
fixture packet by packet, decodes each via the production `PacketHeader.from_buf` +
`PACKET_TYPES[pid]` decoder path, calls `capture._update_data(name, payload)`, and stops at
frame `N`. This means:

- **Production code path** — the exact same decode + cache update logic runs in tests
- **No networking** — the socket and listener thread are never started
- **No API keys** — the MCP functions are called directly as Python functions

## Golden tests and the `--update-golden` flow

The 12 committed golden JSON files in `tests/fixtures/golden/` capture the exact output of
the four pure-read tools at three race scenarios (start, green_steady, finish), with
wall-clock fields stripped by `mask()`.

When an **intentional** format change alters tool output, regenerate the goldens with:

```bash
python tests/fixtures/build_fixture.py --skip-parity --update-golden
```

The `--skip-parity` flag skips the full-source comparison (which requires the 70 MB dev asset).
`--update-golden` overwrites the committed JSON files with the new output. Commit the diff as
part of the format-change PR so the intent is explicit in code review.

## Running the tests

```bash
# All tests (fast — ~5 s)
pytest -v

# With coverage
pytest --cov=src --cov-report=term-missing -v

# One layer only
pytest tests/unit/ -v
pytest tests/deterministic/ -v
pytest tests/integration/ -v
```
