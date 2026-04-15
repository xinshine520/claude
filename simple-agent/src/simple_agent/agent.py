"""Agent - core agent loop implementation."""

import json
import uuid
from typing import Any, AsyncGenerator, Callable
from simple_agent.types import (
    AgentConfig,
    AgentEvent,
    AgentEventType,
    Message,
    MessageRole,
    MessageContent,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    Tool,
    Session,
    SessionStatus,
    LLMInput,
)
from simple_agent.llm.client import LLMClient
from simple_agent.tool.registry import ToolRegistry
from simple_agent.tool.executor import ToolExecutor, ExecutionContext
from simple_agent.config import DEEPSEEK_MODEL


class Agent:
    """
    Multi-turn Agent with tool calling support.

    The agent runs a loop that:
    1. Calls LLM with current messages
    2. If LLM requests tool calls, executes them
    3. Adds tool results back to messages
    4. Repeats until no more tool calls
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_client: LLMClient,
        registry: ToolRegistry,
    ):
        """
        Initialize Agent.

        Args:
            config: Agent configuration.
            llm_client: LLM client instance.
            registry: Tool registry with available tools.
        """
        self.config = config
        self.llm_client = llm_client
        self.registry = registry
        self.executor = ToolExecutor(registry)

    async def run(self, session: Session, user_input: str) -> Message:
        """
        Run agent on a single user input (non-streaming).

        Args:
            session: Session to use.
            user_input: User message content.

        Returns:
            Final assistant message.
        """
        # Add user message
        user_message = Message(
            role=MessageRole.USER,
            content=[TextContent(type="text", text=user_input)],
        )
        session.messages.append(user_message)

        # Run agent loop
        await self._run_loop(session)

        # Return last assistant message
        for msg in reversed(session.messages):
            if msg.role == MessageRole.ASSISTANT:
                return msg

        return session.messages[-1]

    async def run_stream(
        self,
        session: Session,
        user_input: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run agent with streaming output.

        Args:
            session: Session to use.
            user_input: User message content.

        Yields:
            Agent events for real-time feedback.
        """
        # Add user message
        user_message = Message(
            role=MessageRole.USER,
            content=[TextContent(type="text", text=user_input)],
        )
        session.messages.append(user_message)

        session.status = SessionStatus.RUNNING

        # Run streaming loop
        async for event in self._run_stream_loop(session):
            yield event

        session.status = SessionStatus.COMPLETED

    async def _run_loop(self, session: Session) -> None:
        """Run non-streaming agent loop."""
        session.status = SessionStatus.RUNNING
        step = 0

        while step < self.config.max_steps:
            step += 1

            # Call LLM
            response = await self._call_llm(session)

            # Create assistant message
            assistant_message = Message(
                id=f"msg_{uuid.uuid4().hex[:8]}",
                role=MessageRole.ASSISTANT,
                content=response.content,
            )
            session.messages.append(assistant_message)

            # Check for tool calls
            tool_calls = [
                c for c in response.content
                if isinstance(c, ToolCallContent)
            ]

            if not tool_calls:
                # No tool calls, we're done
                session.status = SessionStatus.COMPLETED
                return

            # Execute tools
            ctx = ExecutionContext(
                session_id=session.id,
                message_id=assistant_message.id,
            )

            results = []
            for call in tool_calls:
                result = await self.executor.execute(call, ctx)
                results.append(result)

            # Add tool results message
            tool_message = Message(
                id=f"msg_{uuid.uuid4().hex[:8]}",
                role=MessageRole.TOOL,
                content=results,
            )
            session.messages.append(tool_message)

        # Max steps reached
        session.status = SessionStatus.ERROR

    async def _run_stream_loop(
        self,
        session: Session,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run streaming agent loop."""
        step = 0

        while step < self.config.max_steps:
            step += 1

            yield AgentEvent(
                type=AgentEventType.MESSAGE_START,
                data={"role": "assistant"},
            )

            content: list[MessageContent] = []
            tool_calls: list[ToolCallContent] = []
            text_buffer = ""

            # Stream LLM response
            async for chunk, finish_reason in self.llm_client.stream_chat(
                self._build_llm_input(session)
            ):
                if chunk is None:
                    # Stream complete
                    yield AgentEvent(
                        type=AgentEventType.MESSAGE_END,
                        data={"finish_reason": finish_reason},
                    )
                    break

                if isinstance(chunk, TextContent):
                    text_buffer += chunk.text
                    yield AgentEvent(
                        type=AgentEventType.TEXT,
                        data={"text": chunk.text},
                    )
                elif isinstance(chunk, ToolCallContent):
                    tool_calls.append(chunk)
                    yield AgentEvent(
                        type=AgentEventType.TOOL_CALL,
                        data={
                            "name": chunk.name,
                            "arguments": chunk.arguments,
                            "id": chunk.id,
                        },
                    )

            # Add assistant message
            if text_buffer:
                content.append(TextContent(type="text", text=text_buffer))

            assistant_message = Message(
                id=f"msg_{uuid.uuid4().hex[:8]}",
                role=MessageRole.ASSISTANT,
                content=content + tool_calls,
            )
            session.messages.append(assistant_message)

            # No tool calls, we're done
            if not tool_calls:
                return

            # Execute tools
            ctx = ExecutionContext(
                session_id=session.id,
                message_id=assistant_message.id,
            )

            for call in tool_calls:
                result = await self.executor.execute(call, ctx)
                yield AgentEvent(
                    type=AgentEventType.TOOL_RESULT,
                    data={
                        "name": call.name,
                        "result": result.result,
                        "is_error": result.is_error,
                    },
                )

                # Add tool result to messages
                session.messages.append(Message(
                    id=f"msg_{uuid.uuid4().hex[:8]}",
                    role=MessageRole.TOOL,
                    content=[result],
                ))

    def _build_llm_input(self, session: Session) -> LLMInput:
        """Build LLM input from session."""
        messages = []
        for msg in session.messages:
            # Convert to OpenAI format
            if msg.role == MessageRole.TOOL:
                # Tool results need special handling
                for block in msg.content:
                    if isinstance(block, ToolResultContent):
                        messages.append({
                            "role": "tool",
                            "tool_call_id": block.tool_call_id,
                            "content": block.result,
                        })
            elif msg.role == MessageRole.ASSISTANT:
                # Assistant message may have tool_calls
                text_parts = []
                tool_calls = []
                for block in msg.content:
                    if isinstance(block, TextContent):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolCallContent):
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.arguments),
                            },
                        })

                msg_dict = {
                    "role": "assistant",
                    "content": "".join(text_parts) if text_parts else None,
                }
                if tool_calls:
                    msg_dict["tool_calls"] = tool_calls
                messages.append(msg_dict)
            else:
                # User and system messages
                text = "".join(
                    b.text if isinstance(b, TextContent) else str(b)
                    for b in msg.content
                )
                messages.append({
                    "role": msg.role.value,
                    "content": text,
                })

        return LLMInput(
            model=self.config.model,
            messages=messages,
            system=self.config.system_prompt,
            tools=self.registry.to_tool_definitions(),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    async def _call_llm(self, session: Session) -> Any:
        """Call LLM with current session."""
        llm_input = self._build_llm_input(session)
        return await self.llm_client.chat(llm_input)


class SimpleAgent:
    """
    Simplified agent builder for easy use.

    Example:
        agent = SimpleAgent(model="gpt-4o-mini")
        agent.add_tool("get_weather", get_weather_function, "Get weather for a location")
        result = await agent.run("What's the weather in Tokyo?")
    """

    def __init__(
        self,
        model: str = DEEPSEEK_MODEL,
        system_prompt: str = "",
        api_key: str | None = None,
        base_url: str | None = None,
        use_deepseek: bool = True,
    ):
        """Initialize SimpleAgent.

        Args:
            model: Model name (default: deepseek-chat).
            system_prompt: System prompt for the agent.
            api_key: API key (uses config if None).
            base_url: Custom base URL.
            use_deepseek: If True, use DeepSeek API (default: True).
        """
        self.config = AgentConfig(
            model=model,
            system_prompt=system_prompt,
        )
        self.llm_client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            use_deepseek=use_deepseek,
        )
        self.registry = ToolRegistry()
        self.agent = Agent(self.config, self.llm_client, self.registry)
        self.session = Session(
            model=model,
            system_prompt=system_prompt,
        )

    def add_tool(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        parameters: dict | None = None,
    ) -> None:
        """
        Add a tool to the agent.

        Args:
            name: Tool name.
            func: Async function to execute.
            description: Tool description for LLM.
            parameters: JSON schema for parameters.
        """
        tool = Tool(
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
        )

        async def executor(args: dict) -> str:
            result = await func(**args)
            if isinstance(result, dict):
                return json.dumps(result)
            return str(result)

        self.registry.register(tool, executor)

    async def run(self, user_input: str) -> str:
        """
        Run agent on user input.

        Args:
            user_input: User message.

        Returns:
            Agent response text.
        """
        result = await self.agent.run(self.session, user_input)

        # Extract text content
        for block in result.content:
            if isinstance(block, TextContent):
                return block.text

        return ""

    async def run_stream(
        self,
        user_input: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run agent with streaming.

        Args:
            user_input: User message.

        Yields:
            Agent events.
        """
        async for event in self.agent.run_stream(self.session, user_input):
            yield event
