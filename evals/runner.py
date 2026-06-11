"""Eval runner: seeds each scenario from the fixture, calls the real agent, scores responses.

Usage:
    python -m evals.runner [--judge] [--repeats N] [--scenario ID] [--out PATH]

Requires real API keys in the environment (OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL).
Judge uses JUDGE_API_KEY, JUDGE_BASE_URL, JUDGE_MODEL (defaults to OPENAI_* if unset).
Does NOT require DEEPGRAM_API_KEY or INWORLD_* — the agent never calls STT/TTS.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from evals import report as eval_report  # noqa: E402
from evals.scenarios import FIXTURE_BIN, SCENARIOS, Scenario  # noqa: E402
from evals.scorers import run_all  # noqa: E402

AGENT_TIMEOUT = 30.0


def _make_judge_fn():
    """Return a judge callable that uses the LLM to score response vs rubric."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("JUDGE_API_KEY") or os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("JUDGE_BASE_URL") or os.environ["OPENAI_BASE_URL"],
    )
    model = os.environ.get("JUDGE_MODEL") or os.environ["OPENAI_MODEL"]

    def judge(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
        tools_str = ", ".join(sorted(observed_tools)) if observed_tools else "none"
        prompt = (
            "You are evaluating a Formula 1 race engineer AI assistant.\n\n"
            f"Driver asked: {scenario.driver!r}\n"
            f"Agent replied: {response!r}\n"
            f"Tools the agent actually invoked this turn: {tools_str}\n\n"
            "CALIBRATION — the following are correct and must NOT be penalised:\n"
            "- Rounded/compact notation ('1.1s', 'about two tenths', 'P3') is required style.\n"
            "- Extreme brevity is intentional — the engineer speaks on a radio, not in prose.\n"
            "- Do not demand extra context the driver did not ask for.\n"
            "- Treat the tools list above as ground truth: never fail for 'not calling' a tool that appears there.\n\n"
            f"Rubric: {scenario.rubric}\n\n"
            "Reply with exactly one line: PASS or FAIL, followed by a colon and a brief reason."
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=80,
            temperature=0,
            seed=0,
            store=False,
        )
        text = (resp.choices[0].message.content or "").strip()
        passed = text.upper().startswith("PASS")
        return passed, text

    return judge


def _run_scenario(
    scenario: Scenario,
    agent_loop: asyncio.AbstractEventLoop,
    agent,
    repeats: int,
    tool_log_path: str,
    judge_fn=None,
) -> list[dict[str, Any]]:
    results = []
    for rep in range(repeats):
        # Clear tool log before each run
        open(tool_log_path, "w").close()

        if scenario.callout_event is not None:
            # Rich callout: run through the real build_callout_message builder
            from src.voice_pipeline.callout_specs import build_callout_message

            async def _run_callout_event(_entry=scenario.callout_event, _agent=agent):
                msg = await build_callout_message(_entry, _agent, monitor=None)
                if not msg:
                    return None
                return await _agent.run_callout_async(msg)

            future: Future = asyncio.run_coroutine_threadsafe(_run_callout_event(), agent_loop)
        elif scenario.callout is not None:
            callout_msg = (
                f"[CALLOUT] {scenario.callout}. "
                "Alert the driver with one short engineer radio call."
            )
            future: Future = asyncio.run_coroutine_threadsafe(
                agent.run_callout_async(callout_msg), agent_loop
            )
        else:
            future: Future = asyncio.run_coroutine_threadsafe(
                agent.reply_async(scenario.driver), agent_loop
            )
        try:
            result = future.result(timeout=AGENT_TIMEOUT)
            if result is None:
                response = "<no response>"
            elif isinstance(result, str):
                response = result
            else:
                response = "<no response>"
        except FuturesTimeoutError:
            future.cancel()
            response = "<timeout>"
        except Exception as exc:
            response = f"<error: {exc}>"

        # Read tool calls the MCP subprocess logged
        observed_tools: set[str] = set()
        try:
            for line in Path(tool_log_path).read_text().splitlines():
                entry = json.loads(line)
                observed_tools.add(entry["tool"])
        except Exception:
            pass

        scores = run_all(response, scenario, observed_tools, judge_fn=judge_fn)

        results.append(
            {
                "scenario_id": scenario.id,
                "repeat": rep,
                "frame": scenario.frame_name,
                "driver": scenario.driver,
                "response": response,
                "observed_tools": sorted(observed_tools),
                "scores": {k: {"passed": v[0], "detail": v[1]} for k, v in scores.items()},
            }
        )
        passed_count = sum(1 for v in scores.values() if v[0] is True)
        total_count = sum(1 for v in scores.values() if v[0] is not None)
        status = "PASS" if passed_count == total_count else "FAIL"
        print(
            f"  [{status}] repeat={rep} tools={sorted(observed_tools)!r}\n"
            f"         response: {response!r}"
        )
    return results


def main():
    parser = argparse.ArgumentParser(description="Run F1 agent evals")
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-judge scoring")
    parser.add_argument("--repeats", type=int, default=1, help="Runs per scenario")
    parser.add_argument("--scenario", help="Run a single scenario by id")
    parser.add_argument("--out", help="Output JSON path (default: evals/results/<ts>.json)")
    args = parser.parse_args()

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in SCENARIOS if s.id == args.scenario]
        if not scenarios:
            print(f"No scenario with id {args.scenario!r}. Available: {[s.id for s in SCENARIOS]}")
            sys.exit(1)

    judge_fn = _make_judge_fn() if args.judge else None

    from src.voice_pipeline.agent import RaceEngineerAgent

    all_results: list[dict[str, Any]] = []

    for scenario in scenarios:
        print(f"\n=== {scenario.id} ({scenario.frame_name}, frame={scenario.frame}) ===")
        print(f"    driver: {scenario.driver!r}")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            tool_log_path = tf.name

        # Build the explicit env for the MCP stdio subprocess.
        # mcp's stdio_client uses get_default_environment() (not os.environ) by default,
        # so we must pass all needed vars explicitly via MCPStdioTool(env=...).
        fixture = scenario.fixture_bin or FIXTURE_BIN
        mcp_env = {
            **os.environ,  # inherit everything (PATH, PYTHONPATH, venv, etc.)
            "F1_MCP_FIXTURE": str(fixture),
            "F1_MCP_FIXTURE_FRAME": str(scenario.frame),
            "F1_MCP_TOOL_LOG": tool_log_path,
        }

        agent = RaceEngineerAgent(mcp_env=mcp_env)
        agent_loop = asyncio.new_event_loop()

        def _run_loop(_loop=agent_loop):
            asyncio.set_event_loop(_loop)
            _loop.run_forever()

        t = threading.Thread(target=_run_loop, daemon=True)
        t.start()

        try:
            init_future: Future = asyncio.run_coroutine_threadsafe(agent.init_async(), agent_loop)
            init_future.result(timeout=20.0)

            results = _run_scenario(
                scenario, agent_loop, agent, args.repeats, tool_log_path, judge_fn=judge_fn
            )
            all_results.extend(results)
        finally:
            shutdown_future: Future = asyncio.run_coroutine_threadsafe(
                agent.shutdown_async(), agent_loop
            )
            try:
                shutdown_future.result(timeout=10.0)
            except Exception:
                pass
            agent_loop.call_soon_threadsafe(agent_loop.stop)
            t.join(timeout=3.0)
            Path(tool_log_path).unlink(missing_ok=True)

    print("\n" + "=" * 60)
    eval_report.print_table(all_results)
    out_path = Path(args.out) if args.out else None
    eval_report.save(all_results, out_path)


if __name__ == "__main__":
    main()
