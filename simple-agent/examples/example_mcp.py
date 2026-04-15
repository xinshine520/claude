"""
Example 3: MCP Integration

This example demonstrates how to integrate with an MCP server.
The MCP server provides tools to the agent.

Prerequisites:
    - An MCP server running (e.g., PostgreSQL MCP, Filesystem MCP)
    - Or use the mock MCP server (example_mcp_server.py)

Example MCP servers:
    - pg-mcp: PostgreSQL database queries
    - filesystem-mcp: File operations
    - slack-mcp: Slack integration
"""

import asyncio
import os
import json
from simple_agent import SimpleAgent, MCPConfig, MCPClient, MCPToolAdapter, Tool


async def main():
    print("=== Example 3: MCP Integration ===\n")

    # Option 1: Connect to an existing MCP server
    # Replace with your MCP server configuration

    # Example: Connect to PostgreSQL MCP server
    # mcp_config = MCPConfig(
    #     name="postgres",
    #     command="npx",
    #     args=["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
    # )

    # Example: Connect to Filesystem MCP server
    # mcp_config = MCPConfig(
    #     name="filesystem",
    #     command="npx",
    #     args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"],
    # )

    # For demonstration, we'll show how to integrate with a mock MCP server
    # that provides database-like tools

    print("Note: This example shows the MCP integration pattern.")
    print("To run with a real MCP server, uncomment the configuration below.\n")

    # Example of connecting to a real MCP server
    # async with MCPClient(mcp_config) as client:
    #     adapter = MCPToolAdapter(client)
    #
    #     # Get tools from MCP server
    #     mcp_tools = await adapter.get_tools()
    #
    #     # Create agent and add MCP tools
    #     agent = SimpleAgent(
    #         model="deepseek-chat",
    #         system_prompt="You are a database assistant.",
    #     )
    #
    #     for tool in mcp_tools:
    #         executor = await adapter.create_executor(tool["name"])
    #         agent.registry.register(
    #             Tool(name=tool["name"], description=tool["description"], parameters=tool["parameters"]),
    #             executor
    #         )
    #
    #     # Use the agent with MCP tools
    #     result = await agent.run("Show me all users")

    # For this example, we'll simulate MCP tools directly
    # (This is what you'd get from an MCP server)

    print("Simulating MCP tools from a database server...")
    print()

    # Define tools that would come from an MCP server
    async def query_users(limit: int = 10) -> dict:
        """Query users from database (MCP tool)."""
        # Simulated database response
        return {
            "users": [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
                {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
            ],
            "total": 3,
        }

    async def query_orders(user_id: int = None) -> dict:
        """Query orders from database (MCP tool)."""
        orders = [
            {"id": 1, "user_id": 1, "product": "Widget", "amount": 29.99},
            {"id": 2, "user_id": 1, "product": "Gadget", "amount": 49.99},
            {"id": 3, "user_id": 2, "product": "Thing", "amount": 19.99},
        ]

        if user_id:
            orders = [o for o in orders if o["user_id"] == user_id]

        return {"orders": orders}

    # Create agent (simulating MCP integration)
    agent = SimpleAgent(
        model="deepseek-chat",
        system_prompt="You are a database assistant. Use the tools to query data.",
    )

    # Add MCP-style tools
    agent.add_tool(
        name="query_users",
        func=query_users,
        description="Query users from the database",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of users to return",
                    "default": 10,
                },
            },
        },
    )

    agent.add_tool(
        name="query_orders",
        func=query_orders,
        description="Query orders from the database",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "Filter orders by user ID",
                },
            },
        },
    )

    # Run queries
    print("User: Show me all users")
    response = await agent.run("Show me all users")
    print(f"Agent: {response}\n")

    print("User: What orders does user 1 have?")
    response = await agent.run("What orders does user 1 have?")
    print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
