"""Pure, deterministic scorers for eval responses.

Each scorer takes (response: str, scenario: Scenario, observed_tools: set[str])
and returns (passed: bool, detail: str).
"""

from __future__ import annotations

import re

from evals.scenarios import Scenario

_FORMAT_FORBIDDEN = re.compile(r"[*#`]|^\s*[-•]\s", re.MULTILINE)
_PUNCTUATION_ALLOWED = re.compile(r"[^a-zA-Z0-9 .,?'\"\-/:()%+\n]")

# Sentence boundary: terminal punctuation NOT preceded by a digit (to skip "0.2s", "83.9").
_SENTENCE_END = re.compile(r"(?<!\d)[.!?](?:\s|$)")

# Verbose number/position patterns that violate compact notation.
_VERBOSE_NOTATION = re.compile(
    r"\bposition\s+\d|\blap\s+\d|\btenths?\b|\bhundredths?\b"
    r"|zero point|one point|two point|three point|four point"
    r"|five point|six point|seven point|eight point|nine point",
    re.IGNORECASE,
)


def brevity(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
    words = len(response.split())
    limit = scenario.max_words
    passed = words <= limit
    return passed, f"{words} words (limit {limit})"


def format_check(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
    match = _FORMAT_FORBIDDEN.search(response)
    if match:
        return False, f"Forbidden formatting at pos {match.start()}: {match.group()!r}"
    return True, "no forbidden formatting"


def no_forbidden_phrase(
    response: str, scenario: Scenario, observed_tools: set[str]
) -> tuple[bool, str]:
    if not scenario.must_not_include:
        return True, "n/a"
    lower = response.lower()
    for phrase in scenario.must_not_include:
        if phrase.lower() in lower:
            return False, f"Forbidden phrase found: {phrase!r}"
    return True, "no forbidden phrases"


def grounding(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
    if not scenario.must_include:
        return True, "n/a"
    lower = response.lower()
    missing = [p for p in scenario.must_include if p.lower() not in lower]
    if missing:
        return False, f"Missing expected content: {missing}"
    return True, "all grounding strings present"


def tool_selection(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
    missing = scenario.expect_tools - observed_tools
    extra = observed_tools - scenario.expect_tools - {"get_context_frame"}
    parts = []
    passed = True
    if missing:
        passed = False
        parts.append(f"missing: {sorted(missing)}")
    if extra:
        parts.append(f"extra (ok but unexpected): {sorted(extra)}")
    detail = "; ".join(parts) if parts else f"correct tools: {sorted(observed_tools)}"
    return passed, detail


def single_sentence(
    response: str, scenario: Scenario, observed_tools: set[str]
) -> tuple[bool, str]:
    """Callouts must not exceed max_sentences. No-op for driver scenarios."""
    if scenario.callout is None and scenario.callout_event is None:
        return True, "n/a"
    matches = _SENTENCE_END.findall(response.strip())
    count = len(matches)
    limit = scenario.max_sentences
    passed = count <= limit
    return passed, f"{count} sentence(s) detected (limit {limit})"


def no_question(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
    """Callouts must not ask the driver questions. No-op for driver scenarios."""
    if scenario.callout is None and scenario.callout_event is None:
        return True, "n/a"
    passed = "?" not in response
    return passed, "no question mark" if passed else "question mark found"


def suppressed(response: str, scenario: Scenario, observed_tools: set[str]) -> tuple[bool, str]:
    """Assert the callout was suppressed (empty/no response). No-op unless expect_suppressed."""
    if not scenario.expect_suppressed:
        return True, "n/a"
    passed = not response or response == "<no response>"
    return passed, "suppressed" if passed else f"expected suppression but got: {response!r}"


def compact_notation(
    response: str, scenario: Scenario, observed_tools: set[str]
) -> tuple[bool, str]:
    """Check that numbers/positions use compact form (P3, 0.2s) not verbose prose."""
    if not scenario.check_compact:
        return True, "n/a"
    match = _VERBOSE_NOTATION.search(response)
    if match:
        return False, f"Verbose notation: {match.group()!r}"
    return True, "compact notation used"


ALL_SCORERS = [
    brevity,
    format_check,
    no_forbidden_phrase,
    grounding,
    tool_selection,
    single_sentence,
    no_question,
    compact_notation,
    suppressed,
]


def run_all(
    response: str,
    scenario: Scenario,
    observed_tools: set[str],
    *,
    judge_fn=None,
) -> dict[str, tuple[bool, str]]:
    results: dict[str, tuple[bool, str]] = {}
    for scorer in ALL_SCORERS:
        results[scorer.__name__] = scorer(response, scenario, observed_tools)
    # Skip judge when suppression is expected — no meaningful response to evaluate.
    if judge_fn is not None and scenario.rubric and not scenario.expect_suppressed:
        results["judge"] = judge_fn(response, scenario, observed_tools)
    return results
