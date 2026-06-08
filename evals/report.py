"""Format eval results as a markdown table and write a JSON report."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"

_SCORER_ORDER = [
    "brevity",
    "format_check",
    "no_forbidden_phrase",
    "grounding",
    "tool_selection",
    "single_sentence",
    "no_question",
    "compact_notation",
    "suppressed",
    "judge",
]


def _emoji(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def print_table(all_results: list[dict[str, Any]]) -> None:
    scorers = _SCORER_ORDER
    col_w = max(12, *(len(s) for s in scorers))
    id_w = max(20, *(len(r["scenario_id"]) for r in all_results))
    header = f"{'Scenario':<{id_w}} | " + " | ".join(f"{s:<{col_w}}" for s in scorers)
    print(header)
    print("-" * len(header))
    for r in all_results:
        scores = r.get("scores", {})
        row = f"{r['scenario_id']:<{id_w}} | "
        row += " | ".join(
            f"{_emoji(scores[s]['passed']) if s in scores else 'n/a':<{col_w}}" for s in scorers
        )
        print(row)

    checks = sum(
        1 for r in all_results for v in r.get("scores", {}).values() if v.get("passed") is not None
    )
    n_pass = sum(
        1 for r in all_results for v in r.get("scores", {}).values() if v.get("passed") is True
    )
    pct = (n_pass / checks * 100) if checks else 0
    print(f"\nOverall: {n_pass}/{checks} checks passed ({pct:.0f}%)")


def save(all_results: list[dict[str, Any]], out_path: Path | None = None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        out_path = RESULTS_DIR / f"{ts}.json"
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "results": all_results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nReport written to {out_path}", file=sys.stderr)
    return out_path
