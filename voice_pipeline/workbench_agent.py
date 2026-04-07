from dotenv import load_dotenv
load_dotenv()

from typing import List
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


@dataclass
class Message:
    content: str

SYSTEM_PROMPT = """
# SYSTEM:
You are Bono, an F1 Race Engineer, supporting a player during an F1 game session.  
Your role is to **interpret telemetry data** and **answer the player's questions** clearly, concisely, in racing context, **but in a very brief way to minimize distractions**.
You will act as if you are a real F1 race engineer and not break character.

# STYLE & TONE:
- Answer like a calm, professional race engineer: **SHORT**, precise, supportive. But also be friendly, and casual when required.
- Avoid overwhelming the player with raw telemetry data and values — summarize and highlight only the most relevant points.

# CONVERSATION FLOW:
- If the player asks something vague, politely clarify what metric they want to understand.
- Use real-world racing context in explanations, but adapt to the **F1 game environment** (e.g. ERS modes, fuel mix, tyre life as simulated).

# SAFETY:
- If telemetry is missing, corrupted, or contradictory, explain that the data is not available.
- Never invent car capabilities that aren't in the F1 game (e.g. illegal setup changes).

# EXAMPLES RESPONSES:
- "Radio clear, over."
- "Rear tyres are at eighty five percent. Consider a pit stop within five laps."  
- "Fuel load is zero point eight laps, safe to push for an overtake now."  
- "ERS is nearly depleted. Switch to Medium mode for two laps to recover."  
- "Front left tyre is 15 degrees hotter than ideal. Try easing off steering input in fast corners."

# INPUT CONTEXT:
- The player input might have typos as it's transcribed automatically via AI. Take that into account.

# OUTPUT FORMATTING:
- Keep responses **brief** to minimize distractions. Answer as if you were a real F1 race engineer.
- Do not use filler words or emojis.
- No need to reply with full sentences - only words and values that matter.
- The only punctuation allowed is points "." commas "," and interrogration marks "?".
- When possible, try to write in full letters (Two point Five instead of "2.5", "Plus two seconds" instead of "+2s")

# IMPORTANT NOTE:
- Remember to keep your answer **VERY BRIEF**.

"""

class WorkbenchAgent(RoutedAgent):
    def __init__(
        self, model_client: ChatCompletionClient, model_context: ChatCompletionContext, workbench: Workbench
    ) -> None:
        super().__init__("An F1 race engineer agent")
        self._system_messages: List[LLMMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        self._model_client = model_client
        self._model_context = model_context
        self._workbench = workbench

    @message_handler
    async def handle_user_message(self, message: Message, ctx: MessageContext) -> Message:

        print("[INFO] handle_user_message started")

        # Add the user message to the model context.
        await self._model_context.add_message(UserMessage(content=message.content, source="user"))
        print("---------User Message-----------")
        print(message.content)

        # Run the chat completion with the tools.
        create_result = await self._model_client.create(
            messages=self._system_messages + (await self._model_context.get_messages()),
            tools=(await self._workbench.list_tools()),
            cancellation_token=ctx.cancellation_token,
        )

        # Run tool call loop.
        while isinstance(create_result.content, list) and all(
            isinstance(call, FunctionCall) for call in create_result.content
        ):
            print("---------Function Calls-----------")
            for call in create_result.content:
                print(f'Calling function {call.name}')

            # Add the function calls to the model context.
            await self._model_context.add_message(AssistantMessage(content=create_result.content, source="assistant"))

            # Call the tools using the workbench.
            print("---------Function Call Results-----------")
            results: List[ToolResult] = []
            for call in create_result.content:
                result = await self._workbench.call_tool(
                    call.name, arguments=json.loads(call.arguments), cancellation_token=ctx.cancellation_token
                )
                results.append(result)
                print(f'Got function call result from {result.name}')

            # Add the function execution results to the model context.
            await self._model_context.add_message(
                FunctionExecutionResultMessage(
                    content=[
                        FunctionExecutionResult(
                            call_id=call.id,
                            content=result.to_text(),
                            is_error=result.is_error,
                            name=result.name,
                        )
                        for call, result in zip(create_result.content, results, strict=False)
                    ]
                )
            )

            # Run the chat completion again to reflect on the history and function execution results.
            create_result = await self._model_client.create(
                messages=self._system_messages + (await self._model_context.get_messages()),
                tools=(await self._workbench.list_tools()),
                cancellation_token=ctx.cancellation_token,
            )

        # Now we have a single message as the result.
        assert isinstance(create_result.content, str)

        print("---------Final Response-----------")
        print(create_result.content)

        # Add the assistant message to the model context.
        await self._model_context.add_message(AssistantMessage(content=create_result.content, source="assistant"))

        # Return the result as a message.
        return Message(content=create_result.content)