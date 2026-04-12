from dotenv import load_dotenv
load_dotenv()

from typing import AsyncIterator, Dict, List, Optional
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import ModelFamily
from autogen_core.models import UserMessage, SystemMessage
import json
from dataclasses import dataclass
from typing import List

from autogen_core import (
    FunctionCall,
    MessageContext,
    RoutedAgent,
    message_handler,
)
from autogen_core.model_context import ChatCompletionContext, BufferedChatCompletionContext
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    FunctionExecutionResult,
    FunctionExecutionResultMessage,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from autogen_core.tools import ToolResult, Workbench
from openai import OpenAI
from autogen_ext.tools.mcp import McpWorkbench, StreamableHttpServerParams, StdioServerParams
from autogen_core import AgentId, SingleThreadedAgentRuntime
import asyncio
import os
import sys
from pathlib import Path
from .workbench_agent import *

REPO_ROOT = Path(__file__).resolve().parents[2]
f1_telemetry_server_params = StdioServerParams(
    command=sys.executable or "python",
    args=["-m", "src.mcp.server"],
)

class RaceEngineerAgent:

    def __init__(self) -> None:
        self.model_client = OpenAIChatCompletionClient(
            model=str(os.getenv("BASETEN_MODEL")),
            api_key=str(os.getenv("BASETEN_API_KEY")),
            base_url=str(os.getenv("BASETEN_BASE_URL")),
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": ModelFamily.GPT_4O,
                "structured_output": False,
            },
        )
        self.initialized = False

    async def init_async(self):
        self.workbench = McpWorkbench(f1_telemetry_server_params)
        await self.workbench.start()

        self.runtime = SingleThreadedAgentRuntime()

        await WorkbenchAgent.register(
            runtime=self.runtime,
            type="RaceEngineerAgent",
            factory=lambda: WorkbenchAgent(
                model_client=self.model_client,
                model_context=BufferedChatCompletionContext(buffer_size=100),
                workbench=self.workbench,
            ),
        )

        self.runtime.start()
        print("Runtime initialized successfully")
        self.initialized = True

    async def reply_async(
        self,
        user_text: str,
    ) -> str:
        if not self.initialized:
            await self.init_async()
        msg = await self.runtime.send_message(
            Message(content=user_text),
            recipient=AgentId("RaceEngineerAgent", "default"),
        )

        return msg.content

    def _run_sync(self, coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    def reply(
        self,
        user_text: str,
    ) -> str:
        return self._run_sync(self.reply_async(user_text))
