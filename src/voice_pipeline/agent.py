from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import logging
import os
import queue
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.voice_pipeline.callouts import CalloutMonitor

logger = logging.getLogger(__name__)

from agent_framework import MCPStdioTool
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient

from src import config as _app_config

SYSTEM_PROMPT = """
# SYSTEM:
You are an F1 Race Engineer, supporting a player during an F1 game session.
Your role is to interpret telemetry data and answer the player's questions clearly, concisely, and naturally like a real race engineer.
You will act as if you are a real F1 race engineer and not break character.

# STYLE & TONE:
- Answer like a calm, professional race engineer: SHORT, precise, supportive.
- Sound natural. Do not sound like a software system or telemetry debugger.
- Do not say phrases like "this is not available in telemetry", "this is not logged yet", "not shown", or similar internal-system wording. Never use the word "telemetry" in a reply — speak as a race engineer, not a software system.
- The fuel section is ALWAYS present in the context frame. NEVER mention fuel unless the driver explicitly asks about fuel, fuel delta, or whether they can make the finish. When fuel status is "nominal" there is no concern — do not bring it up. Only when the driver asks about fuel: if status is "nominal", say "Fuel's fine." or give the lap range; if status flags critical, warn them.

# CONVERSATION FLOW:
- Answer ONLY what the player explicitly asked. Nothing else.
- If the player asks about the gap ahead, give the gap ahead. Do not mention the gap behind, tyre temps, nearby drivers, or anything else.
- The context frame contains far more data than the player asked for. Ignore everything in it that is not directly relevant to the question.
- Do not volunteer observations, warnings, or interesting data you noticed in the telemetry.
- Do not ask follow-up questions unless the player explicitly asks for deeper analysis.
- Use real-world racing context in explanations, adapted to the F1 game environment.
- If the driver asks something unrelated to the race, car, or telemetry (jokes, personal questions, anything off-topic), do NOT engage with the content. Decline briefly and redirect: "Focus, we're racing." Do not answer the question. Do not tell jokes.
- The driver message comes from speech-to-text and may be garbled or contain mis-heard words (e.g. a driver's name transcribed as a random word, or filler like "the d bit"). NEVER repeat or echo the garbled words back. Infer the most likely racing intent and answer it. Driver names are always one of the cars in the race — if a name sounds off, match it to the nearest real driver in the field; if you truly cannot tell what was asked, give one short "Say again?" — do not invent a question or a driver.

# TOOL USE:
- The context frame is auto-injected with THIS message and already contains: your position, lap, gap ahead/behind (aheadDriver/behindDriver with names and gap seconds), your tyre compound/age/wear, fuel, ERS, damage, and flags. Questions answerable from these fields need NO tool call — answer directly from the injected frame.
- Do NOT call get_context_frame yourself — it is already provided. Never re-fetch it.
- Call a tool ONLY when the question needs data not in the frame: get_leaderboard (any driver other than the two adjacent cars, or counting/penalties across the field), get_lap_times (sector times), get_strategy (tyre recommendation, pit/rejoin prediction, or pit history), get_weather_forecast (weather). Do not call tools "just in case" — an unnecessary call wastes time and lets the gap value drift mid-answer.
- The context frame's gap section only shows the single car immediately ahead (aheadDriver) and immediately behind (behindDriver) the player. "Ahead" and "behind" are relative to the player's race position — aheadS is the gap to the car that is ahead of you, behindS is the gap to the car that is behind you. If the driver asks about ANY other car — the race leader, P3, a specific driver not in those two slots — you MUST call get_leaderboard.
- If the driver asks about multiple cars in front or behind ("the three cars ahead of me", "who's behind me in P13, P14, P15"), that requires more than the single adjacent driver the frame provides — call get_leaderboard.
- position.grid is the qualifying/grid position. position.current is the live race position. Never confuse them.
- When the driver asks whether they or someone else has pitted: call get_strategy. The currentTyre.compound and currentTyre.ageLaps fields show the current fitted tyre; if it differs from the race-start compound or has age > 0 at a point where it shouldn't, infer a pit has occurred. Do NOT use pitStatus — it only shows whether the car is in the pit lane right now, not whether a pit stop has happened.
- When recommending which tyre compound to fit, ALWAYS call get_strategy first. The lapDeltaMs field in that response shows the pace difference per compound. Do not recommend a compound based on general knowledge — use the data.
- When the driver asks about sector times, call get_lap_times. The context frame does not contain sector data.
- DRS rule: the car directly behind you has DRS available if their gap is less than 1.0s. If the driver asks whether someone behind them can use DRS, check behindDriver and behindS: < 1.0s means yes they have DRS, >= 1.0s means no DRS.

# STRATEGY:
- Tyre choice: do NOT blindly pick the compound with the lowest lapDeltaMs. Cross-check lapsRemaining — a faster-per-lap compound that cannot survive the remaining stint is the wrong call. Pick the compound that is both quick AND durable enough. State the compound and the single deciding factor in one clause: e.g. "Medium — quicker and lasts the stint."
- Undercut / pit timing: reason over all available data — gap to the rival ahead (context frame), pitWindow ideal/latest lap, rejoinPosition, and the tyre pace advantage. State the call and the single strongest reason: e.g. "Box now, you rejoin P5 ahead on fresher mediums." Do not just restate the gap or the question.

# SAFETY:
- If data is missing or not in the feed, respond in-character: say something like "Can't see that from here." or "Not on our screen." Never say "not available", "not shown", or "not in this snapshot" — use natural engineer language.
- Never invent car state that is not in the context frame or a tool response. This includes: clutch settings, brake bias, engine modes, MFD values, traction control level, ERS deployment mode, fuel mix — none of these are in the feed. If asked about any of them, say "Not on our screen."
- The driver's message comes from speech-to-text and may be garbled beyond recognition. If the message does not map to any plausible racing question you can answer with the available data, say "Say again?" — do not guess at a meaning and invent an answer.
- If you call get_leaderboard and a driver is not listed, state they are not in this race. Never invent a position.

# OUTPUT FORMATTING (data Q&A only — does NOT apply to [CALLOUT]):
- Keep responses brief to minimize distractions.
- Do not use filler words or emojis.
- No need to reply with full sentences, only words and values that matter.
- The only punctuation allowed is periods, commas, and question marks.
- Use race-engineer phrasing for numbers. Prefer rounded forms: "about two tenths" not "0.256 seconds".
- No markdown, bullet points, asterisks, or special characters.
- Use compact numeric notation: "0.2s", "P3", "L4".

# IMPORTANT NOTE:
- Keep your answer VERY BRIEF.
- Each request includes both a driver message and a context frame with the latest telemetry snapshot.
- The context frame in THIS message is the only authoritative source of current race state.
- Never use values from earlier messages in the conversation for current telemetry — they are stale.
- If the context frame does not contain what the driver asked for, say so briefly.

# CALLOUTS:
- When the message starts with [CALLOUT], you are radioing the driver about something that just happened — not answering a question.
- [CALLOUT] events are ground truth. Context frame may lag by a second; [CALLOUT] facts override it.
- Output formatting rules above do NOT apply to callouts. Sound like a real radio transmission, not a data readout.
- Never start a response with the driver's name. Dive straight into the information or call.
- Tactical alerts (DRS, yellow, safety car, VSC, penalty): one terse sentence — action or awareness only.
- Competitive events (overtake gained/lost, fastest lap, last lap): one natural sentence with human energy. Not clinical.
- Race-ending events (chequered flag, red flag, retirement): up to two short sentences — brief emotion, then action or reflection.
- Do not ask questions. Do not pad with explanation.

# EXAMPLES:
Data Q&A:
- Driver: "Radio check" → "Loud and clear."
- Driver: "Gap to Verstappen?" → "About 0.2s."
- Driver: "Box box?" → "Not yet, two more laps, box on L4."
- Driver: "Damage?" → "Front wing, minor. Keep an eye on it."
- Driver: "Gap ahead?" → "0.3s." — NOT "0.3s, and Leclerc is closing from behind."

Callouts:
- [CALLOUT] DRS enabled. → "DRS open."
- [CALLOUT] Yellow flag. → "Yellow ahead, lift and stay wide."
- [CALLOUT] Safety car deployed, box now. → "Safety car, box this lap."
- [CALLOUT] Virtual safety car, hold the delta. → "VSC, hold the delta, don't close up."
- [CALLOUT] Red flag. → "Red flag, slow right down, bring it to the pit lane."
- [CALLOUT] Penalty issued to you. → "Penalty for you, we're on it."
- [CALLOUT] Rival penalty. → "Penalty for Verstappen, noted."
- [CALLOUT] Player gained a place past Leclerc, now P3. → "P3! That's it, keep pushing."
- [CALLOUT] Player lost a place to Norris, now P5. → "P5, we've lost a place. Stay composed, we'll come back."
- [CALLOUT] Player set fastest lap, 1:21.456. → "Fastest lap. Beautiful."
- [CALLOUT] Final lap. P1, 1.4s gap to Russell behind. → "Final lap. P1, bring it home clean. You've got this."
- [CALLOUT] Final lap. P3, under pressure from Alonso 0.8s behind. → "Final lap, P3. Don't let Alonso through — defend the line."
- [CALLOUT] Chequered flag. P1, started P3. → "P1! That's a win. Brilliant drive."
- [CALLOUT] Chequered flag. P14, started P8, lost 6 places. → "Chequered flag. P14 from P8 — tough race. We'll look at it."
- [CALLOUT] Retirement, mechanical failure. → "Retirement, mechanical. Bring it in safely. We'll regroup."
"""


MAX_HISTORY_TURNS = 10
SESSION_POLL_INTERVAL = 3.0
# In-character reply when the model times out or returns nothing — keeps the
# race-engineer persona instead of surfacing a system-error string to the driver.
EMPTY_REPLY_FALLBACK = "Say again?"
RACE_SESSION_TYPES = frozenset(_app_config.get("sessionTypes", ["Race", "Race 2", "Feature Race"]))
ACTIVE_PHASES = frozenset({"racing", "sc_vsc", "opening_lap"})


_AGENT_RUN_TIMEOUT = float(os.getenv("F1_AGENT_RUN_TIMEOUT", "7.0"))


class RaceEngineerAgent:
    def __init__(self, mcp_env: dict[str, str] | None = None) -> None:
        self._mcp_env = mcp_env
        self._reasoning_effort: str | None = os.getenv("OPENAI_REASONING_EFFORT") or None
        _client_cls = (
            OpenAIChatCompletionClient
            if os.getenv("OPENAI_USE_COMPLETIONS_API")
            else OpenAIChatClient
        )
        self._client = _client_cls(
            model=str(os.getenv("OPENAI_MODEL")),
            api_key=str(os.getenv("OPENAI_API_KEY")),
            base_url=str(os.getenv("OPENAI_BASE_URL")),
        )
        self._agent = None
        self._mcp_tool: MCPStdioTool | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._history: list[tuple[str, str]] = []
        self._known_names: set[str] = set()
        self._player_name: str | None = None
        self._player_team: str | None = None
        self._session_active: bool = False
        self._session_phase: str = ""
        self._session_type: str = ""
        self._session_ended: bool = False
        self._poll_task: asyncio.Task | None = None
        self._mcp_lock = asyncio.Lock()
        self._last_ptt_ts: float = 0.0
        self._cached_context_frame: dict = {}
        self._last_observed_position: int | None = None

        self._callouts: CalloutMonitor | None = None

    @property
    def last_ptt_ts(self) -> float:
        return self._last_ptt_ts

    @property
    def player_team(self) -> str | None:
        return self._player_team

    def set_callout_queue(self, q: queue.Queue) -> None:
        from src.voice_pipeline.callouts import CalloutMonitor

        self._callouts = CalloutMonitor(self, q)

    async def init_async(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return

            self._mcp_tool = MCPStdioTool(
                name="F1TelemetryServer",
                command=sys.executable or "python",
                args=["-m", "src.mcp.server"],
                allowed_tools=[
                    "get_leaderboard",
                    "get_lap_times",
                    "get_weather_forecast",
                    "get_strategy",
                ],
                env=self._mcp_env,
            )
            await self._mcp_tool.__aenter__()

            self._agent = self._client.as_agent(
                name="RaceEngineerAgent",
                instructions=SYSTEM_PROMPT,
            )
            self._initialized = True
            self._event_last_checked_ts = time.time()
            self._poll_task = asyncio.get_running_loop().create_task(self._poll_session_loop())
            print("Runtime initialized successfully")

    async def shutdown_async(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._mcp_tool is not None:
            try:
                await self._mcp_tool.__aexit__(None, None, None)
            finally:
                self._mcp_tool = None
        self._agent = None
        self._history = []
        self._session_active = False
        self._initialized = False

    async def _fetch_context_frame(self) -> str:
        if self._mcp_tool is None:
            return "{}"
        async with self._mcp_lock:
            raw = await asyncio.wait_for(
                self._mcp_tool.call_tool("get_context_frame"),
                timeout=1.5,
            )
        if isinstance(raw, list) and raw:
            return raw[0].text
        return "{}"

    async def reply_async(self, user_text: str) -> str:
        if not self._initialized:
            await self.init_async()
        assert self._agent is not None

        self._last_ptt_ts = time.time()

        try:
            snapshot = await self._fetch_context_frame()
            self._extract_names_from_snapshot(snapshot)
        except Exception as exc:
            logger.warning("get_context_frame failed: %s", exc)
            snapshot = {"error": f"context_unavailable: {exc}"}

        history_prefix = ""
        if self._history:
            lines = []
            for past_driver, past_reply in self._history[-MAX_HISTORY_TURNS:]:
                lines.append(f"Driver: {past_driver}")
                lines.append(f"Engineer: {past_reply}")
            history_prefix = "Previous exchanges:\n" + "\n".join(lines) + "\n\n"

        request_text = (
            f"{history_prefix}"
            "Context frame, latest telemetry snapshot:\n"
            f"{json.dumps(snapshot, ensure_ascii=True) if isinstance(snapshot, dict) else snapshot}\n\n"
            f"Driver: {user_text}"
        )

        run_kwargs = {"tools": self._mcp_tool} if self._mcp_tool is not None else {}
        _run_options = (
            {"extra_body": {"reasoning_effort": self._reasoning_effort}}
            if self._reasoning_effort
            else None
        )
        try:
            async with self._mcp_lock:
                result = await asyncio.wait_for(
                    self._agent.run(
                        request_text,
                        options=_run_options,
                        client_kwargs={"store": False},
                        **run_kwargs,
                    ),
                    timeout=_AGENT_RUN_TIMEOUT,
                )
        except TimeoutError:
            logger.warning("agent.run timed out after 7s")
            return EMPTY_REPLY_FALLBACK

        text = getattr(result, "text", None)
        if not isinstance(text, str):
            logger.warning(
                "Agent result has no .text string; falling back to str(result). type=%s value=%r",
                type(result),
                result,
            )
            text = str(result)

        # Model can return an empty/whitespace turn (e.g. only tool calls, no final
        # text). Surface a natural in-character prompt instead of silence, and don't
        # poison the history with a blank engineer reply.
        if not text.strip():
            logger.warning("Agent produced an empty reply; returning fallback.")
            return EMPTY_REPLY_FALLBACK

        self._history.append((user_text, text))
        return text

    async def _poll_session_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(SESSION_POLL_INTERVAL)
                await self._refresh_session_state()
                if self._session_active and self._callouts is not None:
                    await self._callouts.check()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Session poll error: %s", exc)

    async def _refresh_session_state(self) -> None:
        if self._mcp_tool is None:
            return
        try:
            snapshot = await self._fetch_context_frame()
            if snapshot == "{}":
                self._session_active = False
                return
            self._extract_names_from_snapshot(snapshot)
            data = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
            self._cached_context_frame = data if isinstance(data, dict) else {}
            ctx = (data or {}).get("context", {})
            session = ctx.get("session", {})
            session_type = session.get("type") or ""
            phase = session.get("phase") or ""
            self._session_type = session_type
            self._session_phase = phase
            now_active = session_type in RACE_SESSION_TYPES and phase in ACTIVE_PHASES
            # Detect race end: phase moves to "finishing" or directly to "not_racing"
            if self._session_active and phase in ("finishing", "not_racing"):
                self._session_ended = True
            if now_active and not self._session_active:
                self._on_session_start()
            self._session_active = now_active
            if now_active and self._callouts is not None:
                await self._check_position_drop(ctx, phase)
        except Exception as exc:
            logger.warning("Session refresh failed: %s", exc)
            self._session_active = False

    async def _check_position_drop(self, ctx: dict, phase: str) -> None:
        """Fire a synthetic callout when the player silently loses 2+ places.

        SC field compression doesn't generate OVTK events, so this fills the gap
        by comparing position across poll ticks.
        """
        player = ctx.get("player", {})
        pos = player.get("position", {})
        current = pos.get("current")
        if not isinstance(current, int):
            return
        prev = self._last_observed_position
        self._last_observed_position = current
        if prev is None or current <= prev:
            return
        places_lost = current - prev
        if places_lost < 2:
            return
        start = pos.get("grid")
        from_label = f"P{prev}" if isinstance(prev, int) else "earlier"
        to_label = f"P{current}"
        start_label = f", started P{start}" if isinstance(start, int) else ""
        sc_note = " under Safety Car" if phase == "sc_vsc" else ""
        callout_msg = (
            f"[CALLOUT] Player lost {places_lost} places{sc_note}, "
            f"now {to_label} from {from_label}{start_label}."
        )
        await self._callouts.fire_synthetic(callout_msg)

    def _on_session_start(self) -> None:
        self._history.clear()
        self._known_names.clear()
        self._player_name = None
        self._player_team = None
        self._session_ended = False
        self._last_observed_position = None
        if self._callouts is not None:
            self._callouts.reset()
        logger.info("New race session started — history and context cleared.")

    # ── Helpers ───────────────────────────────────────────────────

    def is_session_active(self) -> bool:
        return self._session_active

    def get_session_info(self) -> dict:
        return {
            "active": self._session_active,
            "phase": self._session_phase,
            "sessionType": self._session_type,
            "ended": self._session_ended,
        }

    async def _fetch_tool(self, name: str) -> str:
        """Call any MCP tool by name; return raw JSON string or '{}'."""
        if self._mcp_tool is None:
            return "{}"
        try:
            async with self._mcp_lock:
                raw = await asyncio.wait_for(
                    self._mcp_tool.call_tool(name),
                    timeout=1.2,
                )
            if isinstance(raw, list) and raw:
                return raw[0].text
        except Exception as exc:
            logger.debug("_fetch_tool(%s) failed: %s", name, exc)
        return "{}"

    async def fetch_telemetry_snapshot(self) -> dict:
        """Aggregate slim telemetry payload for the /telemetry endpoint."""
        import json as _json

        # get_context_frame is already fetched every 3 s by _poll_session_loop;
        # serve the cached copy here to avoid a redundant MCP call.
        results: dict = {"active": True, "get_context_frame": self._cached_context_frame}
        for tool in ("get_leaderboard", "get_strategy", "get_lap_times"):
            try:
                raw = await self._fetch_tool(tool)
                results[tool] = _json.loads(raw) if raw and raw != "{}" else {}
            except Exception:
                results[tool] = {}
        return results

    def _extract_names_from_snapshot(self, snapshot: str | dict) -> None:
        try:
            data = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
            ctx = data.get("context", {}) if isinstance(data, dict) else {}
            names: list[str] = []
            track = ctx.get("session", {}).get("track")
            if isinstance(track, str):
                names.append(track)
            player = ctx.get("player", {})
            player_name = player.get("name")
            if isinstance(player_name, str):
                names.append(player_name)
                if player_name != "unknown":
                    self._player_name = player_name
            player_team = player.get("team")
            if isinstance(player_team, str) and player_team not in ("unknown", "Unknown"):
                self._player_team = player_team
            gap = ctx.get("player", {}).get("gap", {})
            for key in ("aheadDriver", "behindDriver"):
                driver = gap.get(key)
                if isinstance(driver, dict):
                    n = driver.get("name")
                    if isinstance(n, str):
                        names.append(n)
            self._known_names.update(n for n in names if n and n != "unknown")
        except Exception:
            pass

    def get_stt_keyterms(self) -> list[str]:
        return list(self._known_names)

    def get_player_info(self) -> dict:
        return {"name": self._player_name, "team": self._player_team}

    async def run_callout_async(self, callout_msg: str) -> str | None:
        """Run a [CALLOUT] message through the LLM — no history, no 'Driver:' prefix.

        Used by both CalloutMonitor._fire and the eval runner so both exercise
        the exact production callout prompt.
        """
        if self._agent is None:
            return None
        try:
            snapshot = await self._fetch_context_frame()
        except Exception as exc:
            logger.warning("Callout context frame failed: %s", exc)
            snapshot = "{}"
        request_text = f"Context frame, latest telemetry snapshot:\n{snapshot}\n\n{callout_msg}"
        run_kwargs = {"tools": self._mcp_tool} if self._mcp_tool is not None else {}
        _run_options = (
            {"extra_body": {"reasoning_effort": self._reasoning_effort}}
            if self._reasoning_effort
            else None
        )
        try:
            async with self._mcp_lock:
                result = await asyncio.wait_for(
                    self._agent.run(
                        request_text,
                        options=_run_options,
                        client_kwargs={"store": False},
                        **run_kwargs,
                    ),
                    timeout=_AGENT_RUN_TIMEOUT,
                )
        except TimeoutError:
            logger.warning("run_callout_async timed out for: %s", callout_msg[:60])
            return None
        except Exception as exc:
            logger.warning("run_callout_async failed: %s", exc)
            return None
        text = getattr(result, "text", None)
        return text if isinstance(text, str) and text.strip() else None

    def _run_sync(self, coro):
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "reply() cannot be called from an active event loop. Use await reply_async(...)."
            )
        except RuntimeError as exc:
            if "cannot be called from an active event loop" in str(exc):
                raise
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    def reply(self, user_text: str) -> str:
        return self._run_sync(self.reply_async(user_text))
