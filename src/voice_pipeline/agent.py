from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import os
import sys
from typing import Optional

from agent_framework import MCPStdioTool
from agent_framework.openai import OpenAIChatClient

SYSTEM_PROMPT = """
# SYSTEM:
You are Bono, an F1 Race Engineer, supporting a player during an F1 game session.
Your role is to interpret telemetry data and answer the player's questions clearly, concisely, and naturally like a real race engineer.
You will act as if you are a real F1 race engineer and not break character.

# STYLE & TONE:
- Answer like a calm, professional race engineer: SHORT, precise, supportive.
- Sound natural. Do not sound like a software system or telemetry debugger.
- Do not say phrases like "this is not available in telemetry", "this is not logged yet", or similar internal-system wording.

# CONVERSATION FLOW:
- Answer only what the player asked.
- Do not ask follow-up questions unless the player explicitly asks for deeper analysis.
- Do not add unsolicited updates about tyres, weather, strategy, or other topics not asked by the player.
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
- Each request includes both:
- a driver message
- a context frame with the latest telemetry snapshot
- Use that context frame as the primary source of current race state.

# EXAMPLES:
- Driver: "Radio check"
- Engineer: "Loud and clear."
- Driver: "Gap to Verstappen?"
- Engineer: "About two tenths."
"""


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
        self._session = None

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
            )
            await self._mcp_tool.__aenter__()

            self._agent = self._client.as_agent(
                name="RaceEngineerAgent",
                instructions=SYSTEM_PROMPT,
            )
            self._session = self._agent.create_session() if hasattr(self._agent, "create_session") else None
            self._initialized = True
            print("Runtime initialized successfully")

    async def shutdown_async(self) -> None:
        if self._mcp_tool is not None:
            try:
                await self._mcp_tool.__aexit__(None, None, None)
            finally:
                self._mcp_tool = None
        self._agent = None
        self._session = None
        self._initialized = False

    async def reply_async(self, user_text: str) -> str:
        if not self._initialized:
            await self.init_async()
        assert self._agent is not None

        try:
            snapshot_raw = await self._mcp_tool.call_tool("get_context_frame") if self._mcp_tool is not None else None
            snapshot = str(snapshot_raw)
        except Exception as exc:
            snapshot = {"error": f"context_unavailable: {exc}"}

        request_text = (
            "Context frame, latest telemetry snapshot:\n"
            f"{json.dumps(snapshot, ensure_ascii=True) if isinstance(snapshot, dict) else snapshot}\n\n"
            f"Driver message:\n{user_text}"
        )

        run_kwargs = {"tools": self._mcp_tool} if self._mcp_tool is not None else {}
        if self._session is not None:
            result = await self._agent.run(request_text, session=self._session, **run_kwargs)
        else:
            result = await self._agent.run(request_text, **run_kwargs)

        text = getattr(result, "text", None)
        return text if isinstance(text, str) else str(result)

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
