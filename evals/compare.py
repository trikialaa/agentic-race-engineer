"""Model comparison runner: runs the full eval suite for two LLM backends and
reports pass rates and latency side-by-side.

Usage:
    python -m evals.compare [--judge] [--repeats N] [--scenario ID] [--out PATH]

Model A is read from OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL.
Model B is read from GROQ_API_KEY / GROQ_BASE_URL / GROQ_MODEL.
Judge uses JUDGE_API_KEY / JUDGE_BASE_URL / JUDGE_MODEL (defaults to OPENAI_*).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from evals.scenarios import FIXTURE_BIN, SCENARIOS, Scenario  # noqa: E402
from evals.scorers import run_all  # noqa: E402

AGENT_TIMEOUT = 45.0

RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class ModelConfig:
    label: str
    api_key: str
    base_url: str
    model: str
    reasoning_effort: str | None = None  # e.g. "none" to disable thinking on Groq/Qwen3
    use_completions_api: bool = False  # True → OpenAIChatCompletionClient (Chat Completions)
    rate_limit_delay_s: float = 0.0  # sleep between scenarios to respect provider RPM caps

    def env_patch(self) -> dict[str, str]:
        patch: dict[str, str] = {
            "OPENAI_API_KEY": self.api_key,
            "OPENAI_BASE_URL": self.base_url,
            "OPENAI_MODEL": self.model,
            "OPENAI_USE_COMPLETIONS_API": "1" if self.use_completions_api else "",
        }
        if self.reasoning_effort is not None:
            patch["OPENAI_REASONING_EFFORT"] = self.reasoning_effort
        else:
            patch["OPENAI_REASONING_EFFORT"] = ""
        return patch


def _load_models() -> tuple[ModelConfig, ModelConfig]:
    a = ModelConfig(
        label=os.environ.get("OPENAI_MODEL", "model-a"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        model=os.environ["OPENAI_MODEL"],
    )
    b = ModelConfig(
        label=os.environ.get("CEREBRAS_MODEL", "model-b"),
        api_key=os.environ["CEREBRAS_API_KEY"],
        base_url=os.environ["CEREBRAS_BASE_URL"],
        model=os.environ["CEREBRAS_MODEL"],
        reasoning_effort=None,
        use_completions_api=True,
        rate_limit_delay_s=2.0,
    )
    return a, b


def _make_judge_fn():
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("JUDGE_API_KEY") or os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("JUDGE_BASE_URL") or os.environ["OPENAI_BASE_URL"],
    )
    judge_model = os.environ.get("JUDGE_MODEL") or os.environ["OPENAI_MODEL"]

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
            model=judge_model,
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


def _run_one(
    scenario: Scenario,
    agent_loop: asyncio.AbstractEventLoop,
    agent,
    tool_log_path: str,
    judge_fn=None,
) -> dict[str, Any]:
    open(tool_log_path, "w").close()

    t_start = time.perf_counter()

    if scenario.callout_event is not None:
        from src.voice_pipeline.callout_specs import build_callout_message

        async def _run_callout_event(_entry=scenario.callout_event, _agent=agent):
            msg = await build_callout_message(_entry, _agent, monitor=None)
            if not msg:
                return None
            return await _agent.run_callout_async(msg)

        future: Future = asyncio.run_coroutine_threadsafe(_run_callout_event(), agent_loop)
    elif scenario.callout is not None:
        callout_msg = (
            f"[CALLOUT] {scenario.callout}. Alert the driver with one short engineer radio call."
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
        response = result if isinstance(result, str) else "<no response>"
    except FuturesTimeoutError:
        future.cancel()
        response = "<timeout>"
    except Exception as exc:
        response = f"<error: {exc}>"

    latency_s = round(time.perf_counter() - t_start, 2)

    observed_tools: set[str] = set()
    try:
        for line in Path(tool_log_path).read_text().splitlines():
            entry = json.loads(line)
            observed_tools.add(entry["tool"])
    except Exception:
        pass

    scores = run_all(response, scenario, observed_tools, judge_fn=judge_fn)
    passed_count = sum(1 for v in scores.values() if v[0] is True)
    total_count = sum(1 for v in scores.values() if v[0] is not None)

    return {
        "scenario_id": scenario.id,
        "frame": scenario.frame_name,
        "driver": scenario.driver,
        "response": response,
        "observed_tools": sorted(observed_tools),
        "latency_s": latency_s,
        "scores": {k: {"passed": v[0], "detail": v[1]} for k, v in scores.items()},
        "checks_passed": passed_count,
        "checks_total": total_count,
    }


def _run_model(
    model: ModelConfig,
    scenarios: list[Scenario],
    repeats: int,
    judge_fn=None,
) -> list[dict[str, Any]]:
    print(f"\n{'=' * 60}")
    print(f"MODEL: {model.label}")
    print(f"  base_url: {model.base_url}")
    print("=" * 60)

    # Patch env so RaceEngineerAgent picks up the correct model.
    orig = {
        k: os.environ.get(k)
        for k in (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_REASONING_EFFORT",
            "OPENAI_USE_COMPLETIONS_API",
            "F1_AGENT_RUN_TIMEOUT",
            "CEREBRAS_API_KEY",
            "CEREBRAS_BASE_URL",
            "CEREBRAS_MODEL",
        )
    }
    os.environ.update(model.env_patch())
    os.environ["F1_AGENT_RUN_TIMEOUT"] = "20"

    from src.voice_pipeline.agent import RaceEngineerAgent

    all_results: list[dict[str, Any]] = []

    for scenario in scenarios:
        print(f"\n  --- {scenario.id} ({scenario.frame_name}) ---")
        for rep in range(repeats):
            with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
                tool_log_path = tf.name

            fixture = scenario.fixture_bin or FIXTURE_BIN
            mcp_env = {
                **os.environ,
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
                init_future: Future = asyncio.run_coroutine_threadsafe(
                    agent.init_async(), agent_loop
                )
                init_future.result(timeout=20.0)

                row = _run_one(scenario, agent_loop, agent, tool_log_path, judge_fn=judge_fn)
                row["model"] = model.label
                row["repeat"] = rep
                all_results.append(row)

                status = "PASS" if row["checks_passed"] == row["checks_total"] else "FAIL"
                print(
                    f"    [{status}] rep={rep} latency={row['latency_s']}s "
                    f"tools={row['observed_tools']!r}\n"
                    f"           response: {row['response']!r}"
                )
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

        if model.rate_limit_delay_s > 0:
            time.sleep(model.rate_limit_delay_s)

    # Restore original env
    for k, v in orig.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    return all_results


def _print_comparison(
    a_results: list[dict], b_results: list[dict], model_a: ModelConfig, model_b: ModelConfig
) -> None:
    a_by_id = {r["scenario_id"]: r for r in a_results}
    b_by_id = {r["scenario_id"]: r for r in b_results}
    all_ids = list(dict.fromkeys([r["scenario_id"] for r in a_results + b_results]))

    id_w = max(30, *(len(sid) for sid in all_ids))
    la_w = max(len(model_a.label), 10)
    lb_w = max(len(model_b.label), 10)

    print(f"\n{'=' * 80}")
    print("COMPARISON SUMMARY")
    print(f"{'=' * 80}")
    header = (
        f"{'Scenario':<{id_w}}  "
        f"{'A: ' + model_a.label:<{la_w + 3}}  "
        f"{'B: ' + model_b.label:<{lb_w + 3}}  "
        f"{'Latency A':>10}  {'Latency B':>10}  Winner"
    )
    print(header)
    print("-" * len(header))

    total_a_pass = total_a_checks = 0
    total_b_pass = total_b_checks = 0
    total_a_lat = total_b_lat = 0.0
    n_a = n_b = 0

    for sid in all_ids:
        a = a_by_id.get(sid)
        b = b_by_id.get(sid)

        def _fmt(r: dict | None) -> str:
            if r is None:
                return "n/a"
            return f"{r['checks_passed']}/{r['checks_total']}"

        def _lat(r: dict | None) -> str:
            if r is None:
                return "n/a"
            return f"{r['latency_s']:.1f}s"

        def _winner(a: dict | None, b: dict | None) -> str:
            if a is None or b is None:
                return "-"
            # Prefer higher pass rate; break ties by latency
            a_pct = a["checks_passed"] / a["checks_total"] if a["checks_total"] else 0
            b_pct = b["checks_passed"] / b["checks_total"] if b["checks_total"] else 0
            if a_pct > b_pct:
                return "A"
            if b_pct > a_pct:
                return "B"
            # Equal quality — prefer faster
            return "A" if a["latency_s"] <= b["latency_s"] else "B"

        print(
            f"{sid:<{id_w}}  "
            f"{_fmt(a):<{la_w + 3}}  "
            f"{_fmt(b):<{lb_w + 3}}  "
            f"{_lat(a):>10}  {_lat(b):>10}  {_winner(a, b)}"
        )

        if a:
            total_a_pass += a["checks_passed"]
            total_a_checks += a["checks_total"]
            total_a_lat += a["latency_s"]
            n_a += 1
        if b:
            total_b_pass += b["checks_passed"]
            total_b_checks += b["checks_total"]
            total_b_lat += b["latency_s"]
            n_b += 1

    print("-" * len(header))
    a_pct = total_a_pass / total_a_checks * 100 if total_a_checks else 0
    b_pct = total_b_pass / total_b_checks * 100 if total_b_checks else 0
    a_avg_lat = total_a_lat / n_a if n_a else 0
    b_avg_lat = total_b_lat / n_b if n_b else 0

    print(
        f"{'TOTALS':<{id_w}}  "
        f"{f'{total_a_pass}/{total_a_checks} ({a_pct:.0f}%)':<{la_w + 3}}  "
        f"{f'{total_b_pass}/{total_b_checks} ({b_pct:.0f}%)':<{lb_w + 3}}  "
        f"{f'{a_avg_lat:.1f}s avg':>10}  {f'{b_avg_lat:.1f}s avg':>10}"
    )
    print()
    print(
        f"Quality  winner: {'A (' + model_a.label + ')' if a_pct >= b_pct else 'B (' + model_b.label + ')'}"
    )
    print(
        f"Latency  winner: {'A (' + model_a.label + ')' if a_avg_lat <= b_avg_lat else 'B (' + model_b.label + ')'}"
    )


def _save_comparison(
    a_results: list[dict],
    b_results: list[dict],
    model_a: ModelConfig,
    model_b: ModelConfig,
    out_path: Path | None,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        out_path = RESULTS_DIR / f"compare_{ts}.json"
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "model_a": {"label": model_a.label, "base_url": model_a.base_url, "model": model_a.model},
        "model_b": {"label": model_b.label, "base_url": model_b.base_url, "model": model_b.model},
        "results_a": a_results,
        "results_b": b_results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nComparison report written to {out_path}", file=sys.stderr)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two LLM backends on the F1 eval suite")
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-judge scoring")
    parser.add_argument("--repeats", type=int, default=1, help="Runs per scenario per model")
    parser.add_argument("--scenario", action="append", help="Scenario id(s) to run (repeatable)")
    parser.add_argument("--out", help="Output JSON path")
    args = parser.parse_args()

    model_a, model_b = _load_models()

    scenarios = SCENARIOS
    if args.scenario:
        ids = args.scenario
        scenarios = [s for s in SCENARIOS if s.id in ids]
        missing = [i for i in ids if not any(s.id == i for s in scenarios)]
        if missing:
            print(f"Unknown scenario(s): {missing}. Available: {[s.id for s in SCENARIOS]}")
            sys.exit(1)

    judge_fn = _make_judge_fn() if args.judge else None

    a_results = _run_model(model_a, scenarios, args.repeats, judge_fn=judge_fn)
    b_results = _run_model(model_b, scenarios, args.repeats, judge_fn=judge_fn)

    _print_comparison(a_results, b_results, model_a, model_b)
    _save_comparison(a_results, b_results, model_a, model_b, Path(args.out) if args.out else None)


if __name__ == "__main__":
    main()
