"""Tool Registry - manages available tools."""

from typing import Any, Callable, Awaitable
from simple_agent.types import Tool, ToolDefinition


class ToolRegistry:
    """Registry for managing agent tools."""

    def __init__(self):
        self._tools: dict[str, tuple[Tool, Callable[..., Awaitable[str]]]] = {}

    def register(
        self,
        tool: Tool,
        executor: Callable[..., Awaitable[str]],
    ) -> None:
        """
        Register a tool with its executor.

        Args:
            tool: Tool definition.
            executor: Async function that executes the tool.
        """
        self._tools[tool.name] = (tool, executor)

    def unregister(self, name: str) -> None:
        """
        Unregister a tool.

        Args:
            name: Tool name to remove.
        """
        self._tools.pop(name, None)

    def get(self, name: str) -> tuple[Tool, Callable[..., Awaitable[str]]] | None:
        """
        Get a tool and its executor.

        Args:
            name: Tool name.

        Returns:
            Tuple of (Tool, executor) or None if not found.
        """
        return self._tools.get(name)

    def get_tool(self, name: str) -> Tool | None:
        """Get tool definition by name."""
        entry = self._tools.get(name)
        return entry[0] if entry else None

    def get_executor(self, name: str) -> Callable[..., Awaitable[str]] | None:
        """Get executor function by tool name."""
        entry = self._tools.get(name)
        return entry[1] if entry else None

    def list(self) -> list[Tool]:
        """List all registered tools."""
        return [tool for tool, _ in self._tools.values()]

    def to_tool_definitions(self) -> list[dict[str, Any]]:
        """
        Convert tools to OpenAI function calling format.

        Returns:
            List of tool definitions in OpenAI format.
        """
        definitions = []
        for tool, _ in self._tools.values():
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return definitions
