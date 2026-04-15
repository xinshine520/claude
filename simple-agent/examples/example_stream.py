"""
Example 2: Streaming Response

This example demonstrates how to use streaming for real-time feedback.
"""

import asyncio
import os
from simple_agent import SimpleAgent


async def search_wikipedia(query: str) -> dict:
    """Search Wikipedia (simulated)."""
    # Simulated Wikipedia results
    results = {
        "python": {
            "title": "Python (programming language)",
            "summary": "Python is a high-level, general-purpose programming language...",
            "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        },
        "claude": {
            "title": "Claude (AI assistant)",
            "summary": "Claude is an AI assistant developed by Anthropic...",
            "url": "https://en.wikipedia.org/wiki/Anthropic",
        },
    }

    query_lower = query.lower()
    if query_lower in results:
        return results[query_lower]

    return {"error": f"No results for: {query}"}


async def main():
    # Create agent
    agent = SimpleAgent(
        model="deepseek-chat",
        system_prompt="You are a helpful research assistant.",
    )

    # Add search tool
    agent.add_tool(
        name="search_wikipedia",
        func=search_wikipedia,
        description="Search Wikipedia for information",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
            },
            "required": ["query"],
        },
    )

    print("=== Example 2: Streaming Response ===\n")

    # Use streaming
    print("User: Tell me about Python\n")
    print("Agent: ", end="", flush=True)

    async for event in agent.run_stream("Tell me about Python"):
        if event.type == "text":
            print(event.data["text"], end="", flush=True)
        elif event.type == "tool_call":
            print(f"\n\n[Calling tool: {event.data['name']}]", end="", flush=True)
        elif event.type == "tool_result":
            print(f"\n[Tool result: {event.data['result'][:100]}...]", end="", flush=True)
        elif event.type == "message_end":
            print("\n")

    print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
