# Contributing

## Setup

```bash
# Python dependencies (including dev tools)
pip install -r requirements.txt -r requirements-dev.txt

# Node / Electron (required only if you're working on the UI)
npm ci

# Copy the env template and fill in your API keys
cp .env.example .env
```

## Running the quality gates

```bash
make lint        # ruff check + format check
make typecheck   # mypy on src/mcp/functions + src/udp_parser
make test        # pytest with coverage (floor: 68%)

# Or run all three in sequence:
make lint && make typecheck && make test
```

Pre-commit hooks run ruff automatically on every commit. Install them once with:

```bash
pre-commit install
```

## Running the app

```bash
make run           # full stack (Flask + Electron)
make run-headless  # Flask + MCP only (no Electron, no game required)

# With a captured packet replay instead of a live game:
python helpers/udp_sampler/replay.py --loop &
make run-headless
```

## Test fixture

The test suite uses a committed 3.14 MB binary slice of a Catalunya 2025 race. If you change the
MCP tool output format in a way that intentionally alters the golden JSON snapshots, regenerate
them with:

```bash
python tests/fixtures/build_fixture.py --skip-parity --update-golden
```

To rebuild the fixture from the full 70 MB source capture (dev asset, not committed):

```bash
make fixture
```

See [tests/README.md](tests/README.md) for the full testing strategy.

## Adding a new MCP tool

1. Implement in `src/mcp/functions/<name>.py` and export from `src/mcp/functions/__init__.py`.
2. Register the name in `TOOL_FUNCTIONS` in `src/mcp/tools.py`.
3. Add invariant tests in `tests/deterministic/test_tools_invariants.py` and golden tests in
   `tests/deterministic/test_tools_golden.py`, then regenerate goldens via `--update-golden`.
4. Update `tests/integration/test_tools_registration.py` expectations.
