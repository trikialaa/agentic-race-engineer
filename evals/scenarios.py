"""Eval scenarios: deterministic race-frame seeds + expected agent behaviour."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FIXTURE_BIN = Path(__file__).parent.parent / "tests" / "fixtures" / "race_catalunya_2025.bin"

# Frame indices from tests/fixtures/markers.json
FRAMES = {
    "start": 127,
    "green_steady": 1815,
    "mid_strategy": 5000,
    "finish": 8668,
}


@dataclass
class Scenario:
    id: str
    frame_name: str
    driver: str
    expect_tools: set[str] = field(default_factory=set)
    must_include: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    rubric: str = ""
    # Simple callout scenarios: set this to the event description string.
    # When set, the runner invokes agent.run_callout_async() instead of reply_async().
    callout: str | None = None
    # Rich callout scenarios: pass the full classified event dict (code, details, involvesPlayer).
    # When set, the runner calls build_callout_message(entry, agent) then run_callout_async().
    callout_event: dict | None = None
    # Per-scenario brevity ceiling (words). Callouts use a tight limit.
    max_words: int = 60
    # Maximum allowed sentences (for callout scenarios with richer content).
    max_sentences: int = 1
    # Enable compact_notation scorer for this scenario.
    check_compact: bool = False
    # Assert the callout was suppressed (no response produced).
    expect_suppressed: bool = False

    @property
    def frame(self) -> int:
        return FRAMES[self.frame_name]


SCENARIOS: list[Scenario] = [
    # ─── Ack / brevity ───────────────────────────────────────────────────────
    Scenario(
        id="radio_check",
        frame_name="green_steady",
        driver="Radio check.",
        expect_tools=set(),
        rubric="Should be a very short acknowledgement, 1-5 words. No telemetry, no questions.",
    ),
    # ─── Gap (from context frame, no extra tool) ─────────────────────────────
    Scenario(
        id="gap_ahead_green",
        frame_name="green_steady",
        driver="Gap ahead?",
        expect_tools=set(),
        # At green_steady the context frame has frontS=1.09 to VERSTAPPEN P4.
        must_include=["1."],
        must_not_include=["behind", "hamilton"],
        rubric="Must state the gap ahead (1.09s). Must NOT volunteer the gap behind or name Hamilton.",
        check_compact=True,
    ),
    Scenario(
        id="gap_ahead_finish",
        frame_name="finish",
        driver="Gap to the car ahead?",
        expect_tools=set(),
        # At finish frontS=0.08 to GASLY P16
        must_include=["0."],
        rubric="Very tight gap (0.08s to Gasly). Sub-0.2s. Compact form only.",
        check_compact=True,
    ),
    # ─── Weather (must call get_weather_forecast) ─────────────────────────────
    Scenario(
        id="weather_forecast",
        frame_name="green_steady",
        driver="What's the weather doing?",
        expect_tools={"get_weather_forecast"},
        must_include=["Light Cloud"],
        must_not_include=["box for wet", "switch to inter", "pit for wet", "fit inter"],
        rubric="Should describe current conditions and forecast. No tyre-switch recommendation for dry track with 5% rain.",
    ),
    # ─── Leaderboard (must call get_leaderboard) ──────────────────────────────
    Scenario(
        id="whos_leading",
        frame_name="green_steady",
        driver="Who's leading the race?",
        expect_tools={"get_leaderboard"},
        must_include=["NORRIS"],
        rubric="Must name the leader (Norris). Short, no unsolicited extra info.",
    ),
    Scenario(
        id="position_of_driver",
        frame_name="green_steady",
        driver="Where's Leclerc running?",
        expect_tools={"get_leaderboard"},
        must_include=["P3", "LECLERC"],
        rubric="Must state Leclerc's position (P3). Compact notation.",
    ),
    # ─── Strategy / tyres ────────────────────────────────────────────────────
    Scenario(
        id="current_tyre",
        frame_name="green_steady",
        driver="What tyre am I on?",
        expect_tools=set(),
        must_include=["soft"],
        rubric="Must state tyre compound. Short. Context frame has this — no strategy tool needed.",
    ),
    Scenario(
        id="pit_window",
        frame_name="mid_strategy",
        driver="When should I box?",
        expect_tools=set(),
        rubric="Should give pit window lap or acknowledge it's unknown. Compact form. get_strategy is the right tool.",
    ),
    Scenario(
        id="tyre_choice",
        frame_name="mid_strategy",
        driver="Which tyre should I fit?",
        expect_tools={"get_strategy"},
        rubric="Should recommend a tyre compound based on available sets. Invoke get_strategy.",
    ),
    # ─── Forbidden phrases ───────────────────────────────────────────────────
    Scenario(
        id="no_forbidden_phrases_missing_data",
        frame_name="start",
        driver="What's my fuel delta?",
        expect_tools=set(),
        must_not_include=[
            "not available",
            "not logged",
            "as an AI",
            "telemetry system",
            "I don't have",
        ],
        rubric="Data may be unavailable. Must not break character with tech-system phrases. Brief natural response.",
    ),
    Scenario(
        id="no_markdown_in_reply",
        frame_name="green_steady",
        driver="Give me a full status update.",
        expect_tools=set(),
        must_not_include=["**", "##", "- ", "* ", "```"],
        rubric="Must produce plain text with no markdown. No bullet points, no headers, no bold, no code blocks.",
    ),
    # ─── Lap times ───────────────────────────────────────────────────────────
    Scenario(
        id="lap_pace",
        frame_name="finish",
        driver="What was my last lap?",
        expect_tools=set(),
        must_include=["83"],
        rubric="Should state the lap time (~83.9s). May read from context frame or call get_lap_times.",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # COMPLEX / STRATEGIC SCENARIOS
    # ═══════════════════════════════════════════════════════════════════════════
    Scenario(
        id="undercut_decision",
        frame_name="green_steady",
        driver="Can I undercut Verstappen if I box now?",
        expect_tools={"get_strategy"},
        rubric="Must invoke get_strategy. Should reason about pit window vs current gap (1.09s ahead). "
        "Should reference pit loss, rejoin position, or tyre delta — not just restate the question.",
    ),
    Scenario(
        id="drs_range_behind",
        frame_name="green_steady",
        driver="Is Hamilton close enough to use DRS on me?",
        expect_tools=set(),
        # Hamilton is 0.5s behind at green_steady — within 1s DRS window
        must_include=["0."],
        rubric="Hamilton is 0.5s behind — within DRS range. Agent should confirm yes, within range, "
        "with the gap value. Compact notation. No invented data.",
    ),
    Scenario(
        id="multi_part_gap_and_pace",
        frame_name="finish",
        driver="Gap ahead and what was my last lap?",
        expect_tools=set(),
        # finish: frontS=0.08, lastLapS=83.962
        must_include=["0.", "83"],
        rubric="Must answer both parts: gap ahead (0.08s) and last lap time (~83.9s). "
        "Neither omitted. Compact notation. No extra data volunteered.",
    ),
    Scenario(
        id="pace_vs_behind",
        frame_name="finish",
        driver="Am I quicker than the car behind?",
        expect_tools=set(),
        # At finish deltaBackS=-0.005 (player nearly same pace as Bortoleto behind)
        rubric="deltaBackS is -0.005s — essentially identical pace. Agent should say roughly equal, "
        "or 'about the same'. Should not claim a large gap.",
    ),
    Scenario(
        id="fuel_to_finish",
        frame_name="start",
        driver="Can I make the end on fuel?",
        expect_tools=set(),
        # At start frame fuel is nominal, 2.59 laps remaining, delta -1.41
        must_not_include=["not available", "as an AI", "telemetry system", "I don't have"],
        rubric="Fuel is nominal at start frame. Agent should answer based on available fuel data "
        "without breaking character or inventing values. Brief, confident response.",
    ),
    Scenario(
        id="rejoin_position",
        frame_name="mid_strategy",
        driver="If I box now, where do I come out?",
        expect_tools={"get_strategy"},
        rubric="Must invoke get_strategy to get rejoinPosition. Should state predicted position "
        "or acknowledge it's unknown if data unavailable. Compact notation.",
    ),
    Scenario(
        id="tyre_offset_choice",
        frame_name="finish",
        driver="Medium or hard next stint?",
        expect_tools={"get_strategy"},
        # At finish: medium +725ms, hard +1607ms vs current
        must_include=["medium"],
        rubric="Must invoke get_strategy. Medium is ~900ms faster than hard next stint. "
        "Agent should recommend medium. Brief, no unsolicited strategy monologue.",
    ),
    Scenario(
        id="last_sector",
        frame_name="finish",
        driver="What was my sector 3 time last lap?",
        expect_tools={"get_lap_times"},
        rubric="Must invoke get_lap_times to retrieve sector data. Should report sector 3 time "
        "or acknowledge if unavailable. Compact form.",
    ),
    Scenario(
        id="gap_to_leader",
        frame_name="green_steady",
        driver="How far behind Norris am I?",
        expect_tools={"get_leaderboard"},
        rubric="Must invoke get_leaderboard. Should report gap to leader (P1 Norris) in compact form. "
        "No extra drivers mentioned.",
        check_compact=True,
    ),
    Scenario(
        id="who_is_behind",
        frame_name="green_steady",
        driver="Who's behind me?",
        expect_tools=set(),
        # Context frame has backDriver = Hamilton P6 at green_steady
        must_include=["hamilton"],
        rubric="Context frame has backDriver=Hamilton P6. Should name Hamilton without calling extra tools.",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # EDGE CASES / CHARACTER GUARDS
    # ═══════════════════════════════════════════════════════════════════════════
    Scenario(
        id="formation_huge_gap",
        frame_name="start",
        driver="Gap ahead?",
        expect_tools=set(),
        # At start frame gap is ~80s (formation lap spread)
        must_include=["80"],
        must_not_include=["not available", "as an AI", "unknown"],
        rubric="Gap is ~80s at formation. Agent must report it, not choke or dodge. "
        "Even a large gap is valid data — state it clearly.",
    ),
    Scenario(
        id="photo_finish_gap",
        frame_name="finish",
        driver="How close is the car ahead?",
        expect_tools=set(),
        must_include=["0."],
        rubric="Gap is 0.08s — photo-finish distance. Agent should communicate extreme urgency. "
        "Compact notation essential.",
        check_compact=True,
    ),
    Scenario(
        id="out_of_scope_brake_bias",
        frame_name="green_steady",
        driver="What's my brake bias?",
        expect_tools=set(),
        must_not_include=["not available", "telemetry", "as an AI", "I don't have", "not shown"],
        rubric="Brake bias is not in the F1 telemetry stream. Agent must stay in character — "
        "brief natural response, must NOT invent a value, must not break the race-engineer persona.",
    ),
    Scenario(
        id="off_topic_guard",
        frame_name="green_steady",
        driver="Tell me a joke.",
        expect_tools=set(),
        must_not_include=[
            "**",
            "##",
            "```",
            "why did",
            "what do you call",
            "you call a",
            "knock knock",
        ],
        rubric="Off-topic request. Agent must decline and redirect to the race — NOT tell a joke. "
        "Expected: something like 'Focus, we're racing.' No joke content whatsoever.",
    ),
    Scenario(
        id="absent_driver",
        frame_name="green_steady",
        driver="Where's Schumacher running?",
        expect_tools={"get_leaderboard"},
        must_not_include=["not available", "as an AI", "I don't have"],
        rubric="Schumacher is not in this race. Must invoke get_leaderboard to check. "
        "Should respond in-character that he's not in the race, without tech-system language.",
    ),
    Scenario(
        id="no_unsolicited_extra",
        frame_name="green_steady",
        driver="Gap ahead?",
        expect_tools=set(),
        must_include=["1."],
        must_not_include=["behind", "hamilton"],
        rubric="Gap ahead is 1.09s to Verstappen. Agent must answer ONLY the gap ahead. "
        "Must NOT volunteer Hamilton's gap behind or any other unsolicited data.",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # CALLOUT SCENARIOS
    # ═══════════════════════════════════════════════════════════════════════════
    Scenario(
        id="callout_safety_car",
        frame_name="green_steady",
        callout="Safety Car",
        driver="",  # unused for callout scenarios
        expect_tools=set(),
        must_include=["box"],
        must_not_include=["?"],
        rubric="Safety car callout. Must say 'box' (pit instruction). One sentence. No question.",
        max_words=15,
    ),
    Scenario(
        id="callout_collision_player",
        frame_name="green_steady",
        callout="Collision (involving you)",
        driver="",
        expect_tools=set(),
        must_not_include=["?"],
        rubric="Player-involved collision callout. One sentence. Should acknowledge the incident. "
        "May mention damage check. No question to driver.",
        max_words=20,
    ),
    Scenario(
        id="callout_penalty_drivethrough",
        frame_name="green_steady",
        callout="Penalty Issued (involving you, Drive through)",
        driver="",
        expect_tools=set(),
        must_include=["penalty"],
        must_not_include=["?"],
        rubric="Drive-through penalty callout. One sentence. Must acknowledge the penalty. No question.",
        max_words=15,
    ),
    Scenario(
        id="callout_yellow_flag",
        frame_name="green_steady",
        callout="Yellow Flag",
        driver="",
        expect_tools=set(),
        must_include=["yellow"],
        must_not_include=["?"],
        rubric="Yellow flag callout. One sentence. Must mention yellow. No question.",
        max_words=15,
    ),
    Scenario(
        id="callout_red_flag",
        frame_name="green_steady",
        callout="Red Flag",
        driver="",
        expect_tools=set(),
        must_not_include=["?"],
        rubric="Red flag callout. One sentence. Should mention stopping or pitting. No question.",
        max_words=15,
    ),
    Scenario(
        id="callout_fastest_lap",
        frame_name="green_steady",
        callout="Fastest Lap",
        driver="",
        expect_tools=set(),
        must_not_include=["?"],
        rubric="Fastest lap callout. One sentence. Positive acknowledgement. No question.",
        max_words=15,
    ),
    Scenario(
        id="callout_drs_enabled",
        frame_name="green_steady",
        callout="DRS Enabled",
        driver="",
        expect_tools=set(),
        must_include=["drs"],
        must_not_include=["?"],
        rubric="DRS enabled callout. One sentence. Must mention DRS. No question.",
        max_words=15,
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # SMART CALLOUT SCENARIOS (via build_callout_message)
    # ═══════════════════════════════════════════════════════════════════════════
    Scenario(
        id="callout_red_flag_pits",
        frame_name="green_steady",
        driver="",
        callout_event={
            "code": "RDFL",
            "eventName": "Red Flag",
            "details": {},
            "involvesPlayer": False,
            "severity": "critical",
        },
        must_include=["pit", "slow"],
        must_not_include=["?"],
        rubric="Red flag callout via builder. Must tell driver to slow down and return to pit lane. One or two sentences.",
        max_words=25,
        max_sentences=2,
    ),
    Scenario(
        id="callout_chequered_result",
        frame_name="finish",
        driver="",
        callout_event={
            "code": "CHQF",
            "eventName": "Chequered flag",
            "details": {},
            "involvesPlayer": False,
            "severity": "critical",
        },
        must_not_include=["?"],
        rubric="Chequered flag callout. Must reference finishing position. Tone should match result (encouraging or measured). One or two sentences.",
        max_words=30,
        max_sentences=2,
    ),
    Scenario(
        id="callout_retirement_reason",
        frame_name="green_steady",
        driver="",
        callout_event={
            "code": "RTMT",
            "eventName": "Retirement",
            "details": {"vehicleIdx": 3, "reason": 3, "reasonName": "Terminal damage"},
            "involvesPlayer": False,
            "severity": "relevant",
        },
        must_include=["terminal", "damage"],
        must_not_include=["?"],
        rubric="Rival retirement. Must mention the reason (terminal damage). One sentence. Note the opportunity.",
        max_words=20,
        max_sentences=1,
    ),
    Scenario(
        id="callout_sc_full",
        frame_name="green_steady",
        driver="",
        callout_event={
            "code": "SCAR",
            "eventName": "Safety Car",
            "details": {
                "safetyCarType": 1,
                "safetyCarTypeName": "Full Safety Car",
                "eventType": 0,
                "eventTypeName": "Deployed",
            },
            "involvesPlayer": False,
            "severity": "critical",
        },
        must_include=["box"],
        must_not_include=["?"],
        rubric="Full safety car deployed. Must instruct driver to box this lap. A direct response like 'Safety car, box this lap.' is a PASS. One sentence.",
        max_words=15,
        max_sentences=1,
    ),
    Scenario(
        id="callout_sc_virtual",
        frame_name="green_steady",
        driver="",
        callout_event={
            "code": "SCAR",
            "eventName": "Safety Car",
            "details": {
                "safetyCarType": 2,
                "safetyCarTypeName": "Virtual Safety Car",
                "eventType": 0,
                "eventTypeName": "Deployed",
            },
            "involvesPlayer": False,
            "severity": "critical",
        },
        must_include=["delta"],
        must_not_include=["?", "box"],
        rubric="Virtual safety car (VSC). Must tell driver to hold delta. May say 'VSC' or 'virtual safety car'. Must NOT say box. One sentence.",
        max_words=20,
        max_sentences=1,
    ),
    Scenario(
        id="callout_collision_serious",
        frame_name="finish",
        driver="",
        callout_event={
            "code": "COLL",
            "eventName": "Collision",
            "details": {"vehicle1Idx": 0, "vehicle2Idx": 5},
            "involvesPlayer": True,
            "severity": "critical",
        },
        must_not_include=["?"],
        expect_suppressed=True,
        rubric="Player collision at finish frame — fixture has no damage data above threshold, so builder should suppress the callout silently.",
        max_words=20,
        max_sentences=1,
    ),
]
