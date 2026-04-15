"""
Example: Real MCP Integration

This example demonstrates connecting to a real MCP server.

Usage:
    1. Start the mock MCP server:
       python examples/mock_mcp_server.py

    2. In another terminal, run this example:
       python examples/example_mcp_real.py
"""

import asyncio
import os
import sys
import signal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simple_agent import SimpleAgent, MCPClient, MCPToolAdapter, MCPConfig, Tool


# Global process reference
mcp_process = None


async def start_mock_mcp_server():
    """Start the mock MCP server as a subprocess."""
    global mcp_process

    import subprocess

    mcp_process = subprocess.Popen(
        [sys.executable, "mock_mcp_server.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Give it time to start
    await asyncio.sleep(1)

    print("Mock MCP Server started", file=sys.stderr)
    return mcp_process


async def stop_mock_mcp_server():
    """Stop the mock MCP server."""
    global mcp_process
    if mcp_process:
        mcp_process.terminate()
        await mcp_process.wait()
        print("Mock MCP Server stopped", file=sys.stderr)


async def main():
    print("=== Real MCP Integration Example ===\n")

    # Start mock MCP server
    print("Starting mock MCP server...")
    await start_mock_mcp_server()

    try:
        # Connect to MCP server
        mcp_config = MCPConfig(
            name="mock",
            command=sys.executable,
            args=["mock_mcp_server.py"],
        )

        client = MCPClient(mcp_config)
        await client.connect()

        # Get tools from MCP server
        adapter = MCPToolAdapter(client)
        mcp_tools = await adapter.get_tools()

        print(f"Found {len(mcp_tools)} tools from MCP server:")
        for tool in mcp_tools:
            print(f"  - {tool['name']}: {tool['description']}")
        print()

        # Create agent
        agent = SimpleAgent(
            model="deepseek-chat",
            system_prompt="You are a helpful assistant with access to MCP tools.",
        )

        # Add MCP tools to agent
        for tool_def in mcp_tools:
            tool = Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                parameters=tool_def.get("parameters", {}),
            )
            executor = await adapter.create_executor(tool_def["name"])
            agent.registry.register(tool, executor)

        # Run queries
        print("User: What's the current time?")
        response = await agent.run("What's the current time?")
        print(f"Agent: {response}\n")

        print("User: Please say hello to John")
        response = await agent.run("Please say hello to John")
        print(f"Agent: {response}\n")

        # Disconnect
        await client.disconnect()

    finally:
        # Stop server
        await stop_mock_mcp_server()


if __name__ == "__main__":
    asyncio.run(main())
