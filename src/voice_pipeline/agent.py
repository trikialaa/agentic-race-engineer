from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

from agent_framework import MCPStdioTool
from agent_framework.openai import OpenAIChatClient
from src import config as _app_config

SYSTEM_PROMPT = """
# SYSTEM:
You are an F1 Race Engineer, supporting a player during an F1 game session.
Your role is to interpret telemetry data and answer the player's questions clearly, concisely, and naturally like a real race engineer.
You will act as if you are a real F1 race engineer and not break character.

# STYLE & TONE:
- Answer like a calm, professional race engineer: SHORT, precise, supportive.
- Sound natural. Do not sound like a software system or telemetry debugger.
- Do not say phrases like "this is not available in telemetry", "this is not logged yet", or similar internal-system wording.

# CONVERSATION FLOW:
- Answer ONLY what the player explicitly asked. Nothing else.
- If the player asks about the gap ahead, give the gap ahead. Do not mention the gap behind, tyre temps, nearby drivers, or anything else.
- The context frame contains far more data than the player asked for. Ignore everything in it that is not directly relevant to the question.
- Do not volunteer observations, warnings, or interesting data you noticed in the telemetry.
- Do not ask follow-up questions unless the player explicitly asks for deeper analysis.
- Use real-world racing context in explanations, adapted to the F1 game environment.

# SAFETY:
- If data is missing or unclear, respond naturally and briefly without technical telemetry wording.
- Never invent car capabilities that are not in the F1 game.

# OUTPUT FORMATTING:
- Keep responses brief to minimize distractions.
- Do not use filler words or emojis.
- No need to reply with full sentences, only words and values that matter.
- The only punctuation allowed is points, commas, and question marks.
- Use race-engineer phrasing for numbers. Prefer rounded forms, for example "about two tenths" instead of "zero point two five six seconds".

# IMPORTANT NOTE:
- Keep your answer VERY BRIEF.
- Each request includes both a driver message and a context frame with the latest telemetry snapshot.
- The context frame in THIS message is the only authoritative source of current race state.
- Never use values from earlier messages in the conversation for current telemetry — they are stale.
- If the context frame does not contain what the driver asked for, say so briefly.

# TTS VOICE FORMATTING:
- For urgent situations (safety car, incident, pit window closing, undercut threat): prefix with [say urgently at a fast pace]
- For concern (damage, fuel warning, tyre failure, big gap opening): prefix with [say with concern in a low voice]
- For positive moments (overtake, fastest lap, position gained, gap closing fast): prefix with [say excitedly]
- For everything else: no prefix tag.
- Never combine contradictory instructions in one tag.
- No markdown, bullet points, asterisks, or special characters in your reply.
- Use compact numeric notation: "0.2s" not "two tenths", "P3" not "position three", "L4" not "lap four".

# EXAMPLES:
- Driver: "Radio check"
- Engineer: "Loud and clear."
- Driver: "Gap to Verstappen?"
- Engineer: "About 0.2s."
- Driver: "Box box?"
- Engineer: "[say urgently at a fast pace] Not yet, two more laps, box on L4."
- Driver: "Damage?"
- Engineer: "[say with concern in a low voice] Front wing, minor. Keep an eye on it."
- Driver: "Gap ahead?"
- Engineer: "0.3s." — NOT "0.3s, and Leclerc is closing from behind at 0.2s."
"""


MAX_HISTORY_TURNS = 10
SESSION_POLL_INTERVAL = 3.0  # seconds between background session checks
RACE_SESSION_TYPES = frozenset(_app_config.get("sessionTypes", ["Race", "Race 2", "Race 3"]))
ACTIVE_PHASES = frozenset({"racing", "sc_vsc", "opening_lap"})


class RaceEngineerAgent:
    def __init__(self) -> None:
        self._client = OpenAIChatClient(
            model=str(os.getenv("BASETEN_MODEL")),
            api_key=str(os.getenv("BASETEN_API_KEY")),
            base_url=str(os.getenv("BASETEN_BASE_URL")),
        )
        self._agent = None
        self._mcp_tool: Optional[MCPStdioTool] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        # Slim dialogue history: (driver_text, engineer_reply) — no context frames stored.
        # Context frames are injected fresh each turn and never persisted in history,
        # so prior turns don't accumulate stale telemetry in the LLM's input.
        self._history: list[tuple[str, str]] = []
        # Names accumulated from context frames for STT keyterm boosting.
        self._known_names: set[str] = set()
        self._player_name: str | None = None
        self._player_team: str | None = None
        self._session_active: bool = False
        self._poll_task: asyncio.Task | None = None
        # Serializes all MCP stdio pipe calls to prevent concurrent read/write interleaving.
        self._mcp_lock = asyncio.Lock()

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
                allowed_tools=["get_leaderboard", "get_lap_times", "get_weather_forecast", "get_strategy"],
            )
            await self._mcp_tool.__aenter__()

            self._agent = self._client.as_agent(
                name="RaceEngineerAgent",
                instructions=SYSTEM_PROMPT,
            )
            self._initialized = True
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

    async def reply_async(self, user_text: str) -> str:
        if not self._initialized:
            await self.init_async()
        assert self._agent is not None

        try:
            async with self._mcp_lock:
                snapshot_raw = await asyncio.wait_for(
                    self._mcp_tool.call_tool("get_context_frame"),
                    timeout=1.5,
                ) if self._mcp_tool is not None else None
            # MCPStdioTool returns a list of Content objects; extract .text from the first one.
            if isinstance(snapshot_raw, list) and snapshot_raw:
                snapshot = snapshot_raw[0].text
            else:
                snapshot = str(snapshot_raw)
            self._extract_names_from_snapshot(snapshot)
        except Exception as exc:
            logger.warning("get_context_frame failed: %s", exc)
            snapshot = {"error": f"context_unavailable: {exc}"}

        # Prepend the last N dialogue turns (driver text + replies only, no past snapshots).
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

        # Run stateless — no session — so the framework never accumulates messages.
        # Hold _mcp_lock for the full agent.run() duration so the background poll task
        # cannot interleave its own call_tool call on the shared stdio pipe.
        run_kwargs = {"tools": self._mcp_tool} if self._mcp_tool is not None else {}
        try:
            async with self._mcp_lock:
                result = await asyncio.wait_for(
                    self._agent.run(request_text, **run_kwargs),
                    timeout=7.0,
                )
        except asyncio.TimeoutError:
            logger.warning("agent.run timed out after 7s")
            return "No response — try again."

        text = getattr(result, "text", None)
        if not isinstance(text, str):
            logger.warning("Agent result has no .text string; falling back to str(result). type=%s value=%r", type(result), result)
            text = str(result)

        self._history.append((user_text, text))
        return text

    async def _poll_session_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(SESSION_POLL_INTERVAL)
                await self._refresh_session_state()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Session poll error: %s", exc)

    async def _refresh_session_state(self) -> None:
        if self._mcp_tool is None:
            return
        try:
            async with self._mcp_lock:
                raw = await asyncio.wait_for(
                    self._mcp_tool.call_tool("get_context_frame"),
                    timeout=2.0,
                )
            if isinstance(raw, list) and raw:
                snapshot = raw[0].text
            else:
                self._session_active = False
                return
            self._extract_names_from_snapshot(snapshot)
            data = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
            ctx = (data or {}).get("context", {})
            session = ctx.get("session", {})
            session_type = session.get("type") or ""
            phase = session.get("phase") or ""
            now_active = session_type in RACE_SESSION_TYPES and phase in ACTIVE_PHASES
            if now_active and not self._session_active:
                self._on_session_start()
            self._session_active = now_active
        except Exception as exc:
            logger.warning("Session refresh failed: %s", exc)
            self._session_active = False

    def _on_session_start(self) -> None:
        self._history.clear()
        self._known_names.clear()
        self._player_name = None
        self._player_team = None
        logger.info("New race session started — history and context cleared.")

    def is_session_active(self) -> bool:
        return self._session_active

    def get_session_info(self) -> dict:
        return {"active": self._session_active}

    def _extract_names_from_snapshot(self, snapshot: str | dict) -> None:
        try:
            data = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
            ctx = data.get("context", {}) if isinstance(data, dict) else {}
            names: list[str] = []
            # Track name
            track = ctx.get("session", {}).get("track")
            if isinstance(track, str):
                names.append(track)
            # Player name
            player = ctx.get("player", {})
            player_name = player.get("name")
            if isinstance(player_name, str):
                names.append(player_name)
                if player_name != "unknown":
                    self._player_name = player_name
            player_team = player.get("team")
            if isinstance(player_team, str) and player_team not in ("unknown", "Unknown"):
                self._player_team = player_team
            # Adjacent drivers
            gap = ctx.get("player", {}).get("gap", {})
            for key in ("frontDriver", "backDriver"):
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

    def _run_sync(self, coro):
        try:
            asyncio.get_running_loop()
            raise RuntimeError("reply() cannot be called from an active event loop. Use await reply_async(...).")
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
