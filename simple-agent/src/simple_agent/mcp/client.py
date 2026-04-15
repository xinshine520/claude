"""MCP Client - integrate with MCP servers."""

import json
import asyncio
from typing import Any
from dataclasses import dataclass


@dataclass
class MCPConfig:
    """MCP server configuration."""
    name: str
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


class MCPClient:
    """
    Client for connecting to MCP servers.

    Supports stdio transport for local MCP servers.
    """

    def __init__(self, config: MCPConfig):
        self.config = config
        self._process: asyncio.subprocess.Process | None = None

    async def connect(self) -> None:
        """Connect to MCP server."""
        cmd = [self.config.command] + (self.config.args or [])

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.config.env,
        )

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        List available tools from MCP server.

        Returns:
            List of tool definitions.
        """
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }

        response = await self._send_request(request)
        return response.get("result", {}).get("tools", [])

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Call a tool on the MCP server.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result.
        """
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }

        response = await self._send_request(request)
        return response.get("result", {})

    async def _send_request(self, request: dict) -> dict:
        """Send JSON-RPC request to MCP server."""
        if not self._process:
            raise RuntimeError("Not connected to MCP server")

        # Send request
        request_data = json.dumps(request).encode() + b"\n"
        self._process.stdin.write(request_data)
        await self._process.stdin.drain()

        # Read response
        response_data = await self._process.stdout.readline()
        response = json.loads(response_data.decode())

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response


class MCPToolAdapter:
    """
    Adapter to convert MCP tools to SimpleAgent tools.
    """

    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client

    async def get_tools(self) -> list[dict[str, Any]]:
        """Get tools from MCP server in SimpleAgent format."""
        mcp_tools = await self.mcp_client.list_tools()

        tools = []
        for tool in mcp_tools:
            tools.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {}),
            })

        return tools

    async def create_executor(self, tool_name: str):
        """
        Create an executor function for a specific MCP tool.

        Args:
            tool_name: Name of the tool.

        Returns:
            Async function that executes the tool via MCP.
        """
        async def executor(args: dict) -> str:
            result = await self.mcp_client.call_tool(tool_name, args)
            return json.dumps(result)

        return executor
