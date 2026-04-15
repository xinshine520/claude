"""
Example 1: Basic Usage

This example demonstrates how to create a simple agent with custom tools.
"""

import asyncio
from simple_agent import SimpleAgent


# Define custom tools
async def get_weather(location: str, unit: str = "celsius") -> dict:
    """Get weather for a location."""
    # In real implementation, call weather API
    weather_data = {
        "tokyo": {"temp": 22, "condition": "sunny", "humidity": 65},
        "beijing": {"temp": 18, "condition": "cloudy", "humidity": 45},
        "new york": {"temp": 15, "condition": "rainy", "humidity": 80},
    }

    location_lower = location.lower()
    if location_lower in weather_data:
        data = weather_data[location_lower]
        temp = data["temp"]
        if unit == "fahrenheit":
            temp = temp * 9 / 5 + 32
        return {
            "location": location,
            "temperature": temp,
            "unit": unit,
            "condition": data["condition"],
            "humidity": data["humidity"],
        }

    return {"error": f"Unknown location: {location}"}


async def calculate(expression: str) -> dict:
    """Calculate a math expression."""
    try:
        # WARNING: eval is unsafe in production!
        result = eval(expression)  # noqa: S307
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


async def main():
    # Create agent with DeepSeek (default)
    agent = SimpleAgent(
        system_prompt="You are a helpful assistant with access to tools.",
    )

    # Add tools
    agent.add_tool(
        name="get_weather",
        func=get_weather,
        description="Get current weather for a location",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name (e.g., Tokyo, Beijing, New York)",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit",
                    "default": "celsius",
                },
            },
            "required": ["location"],
        },
    )

    agent.add_tool(
        name="calculate",
        func=calculate,
        description="Calculate a mathematical expression",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression (e.g., 2+2, 10*5)",
                },
            },
            "required": ["expression"],
        },
    )

    # Run agent
    print("=== Example 1: Basic Usage ===\n")

    # Weather query
    print("User: What's the weather in Tokyo?")
    response = await agent.run("What's the weather in Tokyo?")
    print(f"Agent: {response}\n")

    # Calculation query
    print("User: What is 125 * 8?")
    response = await agent.run("What is 125 * 8?")
    print(f"Agent: {response}\n")

    # Multi-step query
    print("User: What's the weather in New York in Fahrenheit?")
    response = await agent.run("What's the weather in New York in Fahrenheit?")
    print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
