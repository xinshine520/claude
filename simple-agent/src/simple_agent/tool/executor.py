"""Tool Executor - executes tool calls."""

import json
from typing import Any
from simple_agent.types import ToolCallContent, ToolResultContent, ToolResult
from simple_agent.tool.registry import ToolRegistry


class ExecutionContext:
    """Context for tool execution."""

    def __init__(
        self,
        session_id: str,
        message_id: str,
        abort_signal: Any = None,
    ):
        self.session_id = session_id
        self.message_id = message_id
        self.abort_signal = abort_signal


class ToolExecutor:
    """Executes tool calls."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(
        self,
        call: ToolCallContent,
        ctx: ExecutionContext,
    ) -> ToolResultContent:
        """
        Execute a tool call.

        Args:
            call: Tool call to execute.
            ctx: Execution context.

        Returns:
            Tool result content.
        """
        executor = self.registry.get_executor(call.name)

        if not executor:
            return ToolResultContent(
                type="tool_result",
                tool_call_id=call.id,
                result=f"Tool not found: {call.name}",
                is_error=True,
            )

        try:
            result = await executor(call.arguments)
            return ToolResultContent(
                type="tool_result",
                tool_call_id=call.id,
                result=result,
                is_error=False,
            )
        except Exception as error:
            return ToolResultContent(
                type="tool_result",
                tool_call_id=call.id,
                result=str(error),
                is_error=True,
            )

    async def execute_with_retry(
        self,
        call: ToolCallContent,
        ctx: ExecutionContext,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> ToolResultContent:
        """
        Execute tool with retry on failure.

        Args:
            call: Tool call to execute.
            ctx: Execution context.
            max_retries: Maximum retry attempts.
            base_delay: Base delay between retries (seconds).

        Returns:
            Tool result content.
        """
        last_error = None

        for attempt in range(max_retries):
            result = await self.execute(call, ctx)

            if not result.is_error:
                return result

            last_error = result.result

            if attempt < max_retries - 1:
                import asyncio
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        return ToolResultContent(
            type="tool_result",
            tool_call_id=call.id,
            result=f"Failed after {max_retries} attempts: {last_error}",
            is_error=True,
        )
