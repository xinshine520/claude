"""LLM Client using OpenAI SDK (compatible with DeepSeek)."""

import json
from typing import Any, AsyncGenerator
from openai import AsyncOpenAI
from simple_agent.types import (
    LLMInput,
    LLMOutput,
    MessageContent,
    TextContent,
    ToolCallContent,
    Message,
    MessageRole,
)
from simple_agent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL


class LLMClient:
    """OpenAI-compatible LLM client with streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        use_deepseek: bool = True,
    ):
        """
        Initialize LLM client.

        Args:
            api_key: API key. If None and use_deepseek=True, uses config.
            base_url: Custom base URL for OpenAI-compatible APIs.
            use_deepseek: If True, use DeepSeek API by default.
        """
        if use_deepseek and base_url is None:
            base_url = DEEPSEEK_BASE_URL
            if api_key is None:
                api_key = DEEPSEEK_API_KEY

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    async def chat(
        self,
        input: LLMInput,
    ) -> LLMOutput:
        """
        Non-streaming chat completion.

        Args:
            input: LLM input parameters.

        Returns:
            LLM output with content and metadata.
        """
        messages = self._build_messages(input)
        tools = input.tools if input.tools else None

        response = await self.client.chat.completions.create(
            model=input.model,
            messages=messages,
            tools=tools,
            temperature=input.temperature,
            max_tokens=input.max_tokens,
        )

        choice = response.choices[0]
        content = self._parse_content(choice.message)

        return LLMOutput(
            content=content,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    async def stream_chat(
        self,
        input: LLMInput,
    ) -> AsyncGenerator[tuple[MessageContent | None, str], None]:
        """
        Streaming chat completion.

        Args:
            input: LLM input parameters.

        Yields:
            Tuple of (content chunk, finish reason)
        """
        messages = self._build_messages(input)
        tools = input.tools if input.tools else None

        response = await self.client.chat.completions.create(
            model=input.model,
            messages=messages,
            tools=tools,
            temperature=input.temperature,
            max_tokens=input.max_tokens,
            stream=True,
        )

        text_content = ""
        tool_calls: dict[str, dict[str, Any]] = {}
        finish_reason = "stop"

        async for chunk in response:
            delta = chunk.choices[0].delta

            # Handle text delta
            if delta.content:
                text_content += delta.content
                yield TextContent(type="text", text=delta.content), ""

            # Handle tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.id:
                        if tc.id not in tool_calls:
                            tool_calls[tc.id] = {
                                "id": tc.id,
                                "name": tc.function.name or "",
                                "arguments": tc.function.arguments or "",
                            }
                        else:
                            if tc.function.name:
                                tool_calls[tc.id]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[tc.id]["arguments"] += tc.function.arguments

            # Check finish reason
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        # Yield accumulated tool calls
        for call_id, call_data in tool_calls.items():
            try:
                args = json.loads(call_data["arguments"]) if call_data["arguments"] else {}
            except json.JSONDecodeError:
                args = {"raw": call_data["arguments"]}

            yield ToolCallContent(
                type="tool_call",
                id=call_id,
                name=call_data["name"],
                arguments=args,
            ), finish_reason

        # Signal completion
        yield None, finish_reason

    def _build_messages(self, input: LLMInput) -> list[dict[str, Any]]:
        """Build OpenAI message format from internal messages."""
        messages: list[dict[str, Any]] = []

        if input.system:
            messages.append({"role": "system", "content": input.system})

        for msg in input.messages:
            if isinstance(msg, Message):
                role = msg.role.value if hasattr(msg.role, 'value') else msg.role

                # Handle tool results specially
                if role == "tool":
                    for block in msg.content:
                        if isinstance(block, ToolResultContent):
                            messages.append({
                                "role": "tool",
                                "tool_call_id": block.tool_call_id,
                                "content": block.result,
                            })
                    continue

                # Handle regular messages
                content = self._message_to_content(msg)
                messages.append({
                    "role": role,
                    "content": content,
                })
            elif isinstance(msg, dict):
                # Pass through dict messages as-is (already in OpenAI format)
                messages.append(msg)
            else:
                content = str(msg)
                messages.append({
                    "role": "user",
                    "content": content,
                })

        return messages

    def _message_to_content(self, msg: Message) -> str:
        """Convert message to string content for OpenAI."""
        parts = []
        for block in msg.content:
            if isinstance(block, TextContent):
                parts.append(block.text)
            elif isinstance(block, ToolCallContent):
                # Should not happen in input messages
                pass
            elif isinstance(block, ToolResultContent):
                parts.append(f"[Tool Result]: {block.result}")
        return "\n".join(parts) or ""

    def _parse_content(self, message: Any) -> list[MessageContent]:
        """Parse OpenAI response to internal content format."""
        content: list[MessageContent] = []

        # Handle text content
        if message.content:
            content.append(TextContent(type="text", text=message.content))

        # Handle tool calls
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}

                content.append(ToolCallContent(
                    type="tool_call",
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return content
