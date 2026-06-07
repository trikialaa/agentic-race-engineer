## Summary

<!-- What does this PR change and why? -->

## Test plan

- [ ] `make lint` passes (`ruff check` + `ruff format --check`)
- [ ] `make typecheck` passes (`mypy`)
- [ ] `make test` passes (all tests green, coverage ≥ 68%)
- [ ] If adding a new MCP tool: registered in `src/mcp/tools.py`, reflected in `tests/integration/test_tools_registration.py`
- [ ] If changing tool output format: golden JSON files updated via `python tests/fixtures/build_fixture.py --skip-parity --update-golden`
