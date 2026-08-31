# Eval harness

The deterministic test suite proves the telemetry *tools* are correct. The eval harness measures
whether the *agent* — given a driver question and a real race frame — selects the right MCP tool,
grounds its answer in the telemetry, and obeys the race-engineer style contract.

## Why evals are separate from tests

LLM responses are non-deterministic and calling a real model costs money. Running evals on every
push would make CI non-reproducible and expensive. Instead, evals are an **on-demand quality
gate**: triggered manually (`workflow_dispatch`) or on a weekly schedule, never on pull requests.

The programmatic scorers (brevity, format, grounding, tool-selection) are deterministic and could
theoretically run in CI — but they require a real agent turn against a real LLM, which is the
expensive part. Separating them keeps the evaluation concept coherent: a pass/fail report for a
non-deterministic system.

## Deterministic scenario seeding

Every scenario is pinned to a real race frame from the Catalunya fixture. Before the agent is
called, the fixture is replayed in-process into a frozen `F1TelemetryCapture`. The MCP
subprocess the agent spawns inherits the environment and serves tools from that frozen state — so
only the *LLM* varies between runs. The fixture itself was validated against the full 70 MB source
via the parity gate described in [tests/README.md](../tests/README.md).

## Scorer taxonomy

| Scorer | Type | Active when | What it protects |
|---|---|---|---|
| `brevity` | programmatic | always | Response under `max_words` (default 60; callouts use 15) |
| `format_check` | programmatic | always | No markdown (`*`, `#`, `` ` ``) — system prompt forbids it |
| `no_forbidden_phrase` | programmatic | always | No "not available", "as an AI", tech-system leakage |
| `grounding` | programmatic | `must_include` set | Key values (driver names, gap values) appear in the reply |
| `tool_selection` | programmatic | always | LLM called the expected MCP tools (and not unnecessary ones) |
| `single_sentence` | programmatic | callout scenarios | Callout contract: exactly one sentence, no run-on responses |
| `no_question` | programmatic | callout scenarios | Callout contract: engineer never asks the driver a question |
| `compact_notation` | programmatic | `check_compact=True` | No verbose forms ("position 3", "tenths") — must use P3, 0.2s |
| `judge` | LLM-as-judge | `--judge` flag | Holistic quality vs. each scenario's rubric |

The programmatic scorers are cheap and catch regressions in style, format, and tool-calling
behaviour. The judge catches subtler quality regressions — a correct value stated awkwardly, a
technically accurate but unhelpfully verbose reply — at the cost of a second LLM call per
scenario.

## Running locally

```bash
# Requires: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL in your .env
make evals

# With LLM-as-judge scoring
python -m evals.runner --judge

# Specific scenario, 3 repeats (pass rate for nondeterministic stability)
python -m evals.runner --scenario gap_ahead_green --repeats 3

# Custom output path
python -m evals.runner --out /tmp/my_eval.json
```

Results are written to `evals/results/<timestamp>.json` (gitignored) and a markdown table is
printed to stdout.

## Callout scenarios

The autonomous `CalloutMonitor` fires radio messages when race events occur (safety car,
penalties, collisions, etc.) without waiting for the driver to speak. These use a different
entry path than driver questions: the `[CALLOUT] {event}. Alert the driver...` message is passed
to `agent.run_callout_async()`, which fetches a context frame and calls the LLM directly — no
conversation history, no `Driver:` prefix.

Callout scenarios use the `callout` field instead of `driver`:

```python
Scenario(
    id="callout_safety_car",
    frame_name="green_steady",
    callout="Safety Car",  # event description string
    driver="",  # unused
    must_include=["box"],  # must instruct the driver to pit
    must_not_include=["?"],  # callout contract: no questions
    max_words=15,  # tight brevity ceiling for one-sentence callouts
)
```

The `single_sentence` and `no_question` scorers are automatically activated for any scenario
with `callout` set. The eval runner builds:

```
[CALLOUT] Safety Car. Alert the driver with one short engineer radio call.
```

and feeds it through the production callout path.

## Adding a scenario

Edit [evals/scenarios.py](../evals/scenarios.py). Each `Scenario` takes:

- `id` — unique slug used in `--scenario` and the report.
- `frame_name` — one of `start`, `green_steady`, `mid_strategy`, `finish` (defined in
  `tests/fixtures/markers.json`).
- `driver` — the spoken question string the agent receives (unused for callout scenarios).
- `callout` — set instead of `driver` for callout evals; the event description string.
- `expect_tools` — set of MCP tool names the LLM *must* invoke (empty = context frame only).
- `must_include` — substrings that must appear in the response (ground truth values).
- `must_not_include` — forbidden phrases (style contract violations).
- `rubric` — plain-English quality description for the LLM judge.
- `max_words` — per-scenario brevity ceiling (default 60; callouts use 15).
- `check_compact` — set to `True` to enable the `compact_notation` scorer.

To find ground-truth values for a new frame, check the committed golden JSONs in
`tests/fixtures/golden/` or run `python -m evals.runner --scenario <id>` once with `--judge` to
see what the agent actually produces.

## Scenario coverage

The suite spans four categories:

1. **Simple** (12) — basic single-fact questions: radio check, gap ahead, weather, leaderboard, tyres, lap times.
2. **Complex / strategic** (10) — multi-part questions, undercut decisions, tyre offset choices, rejoin positions.
3. **Edge cases / character guards** (6) — huge formation gaps, photo-finish gaps, out-of-scope data, off-topic deflection, absent drivers, unsolicited-extra guard.
4. **Callouts** (7) — safety car, collision, penalty, yellow/red flag, fastest lap, DRS.

## Reading the report

The markdown table shows `PASS`/`FAIL` per scenario × scorer. The JSON file contains the full
response text, observed tool calls, and per-scorer detail strings for debugging failures.

A scenario fails `tool_selection` if the LLM skipped an expected tool or added unnecessary ones.
`grounding` failure means the response did not contain a key value the fixture guarantees is
present. `judge` failure requires reading the detail string — it contains the LLM's brief reason.
