# Simple Agent SDK

A simple multi-turn agent SDK built with DeepSeek (OpenAI-compatible), supporting custom tools and MCP integration.

## Features

- **Multi-turn Agent Loop**: Automatically handles tool calling and response iteration
- **Tool Support**: Add custom tools with JSON Schema parameter definitions
- **MCP Integration**: Connect to MCP servers for dynamic tool loading
- **Streaming Support**: Real-time streaming responses
- **Simple API**: Easy-to-use `SimpleAgent` class for quick setup
- **DeepSeek by Default**: Pre-configured for DeepSeek API

## Installation

```bash
cd simple-agent
pip install -e .
```

Or install dependencies only:

```bash
pip install openai pydantic
```

## Quick Start

```python
import asyncio
from simple_agent import SimpleAgent

# Create agent (uses DeepSeek by default)
agent = SimpleAgent()

# Add a tool
async def get_weather(location: str) -> dict:
    return {"temp": 22, "condition": "sunny"}

agent.add_tool(
    name="get_weather",
    func=get_weather,
    description="Get weather for a location",
    parameters={
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"}
        },
        "required": ["location"]
    }
)

# Run agent
result = await agent.run("What's the weather in Tokyo?")
print(result)
```

## Examples

See the `examples/` directory for more detailed examples:

1. **example_basic.py** - Basic usage with custom tools
2. **example_stream.py** - Streaming response example
3. **example_mcp.py** - MCP integration pattern
4. **example_mcp_real.py** - Real MCP server connection

## API Reference

### SimpleAgent

The easiest way to create an agent.

```python
agent = SimpleAgent(
    model="gpt-4o-mini",           # OpenAI model
    system_prompt="You are helpful", # System prompt
    api_key=None,                   # OpenAI API key (uses env var if None)
    base_url=None,                  # For OpenAI-compatible APIs
)

agent.add_tool(name, func, description, parameters)
result = await agent.run("your message")

# Or streaming
async for event in agent.run_stream("your message"):
    # Handle events
    pass
```

### Core Classes

- `Agent`: Full-featured agent with session management
- `LLMClient`: OpenAI API client
- `ToolRegistry`: Tool registration and management
- `ToolExecutor`: Tool execution with error handling
- `MCPClient`: Connect to MCP servers
- `MCPToolAdapter`: Adapt MCP tools to SimpleAgent format

### Types

- `Message`, `Session`: Chat message and session
- `Tool`, `ToolResult`: Tool definitions
- `AgentEvent`: Streaming events
- `AgentConfig`: Agent configuration

## Configuration

The SDK is pre-configured to use DeepSeek API. Configuration is stored in `src/simple_agent/config.py`:

```python
DEEPSEEK_API_KEY = "sk-..."  # Your API key
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
```

You can override these in code:

```python
agent = SimpleAgent(
    model="deepseek-chat",  # or custom model
    api_key="your-key",
    base_url="custom-url",  # for OpenAI-compatible APIs
    use_deepseek=False,     # disable to use OpenAI
)
```

## Design

Based on the design specification in `specs/0010-simple-agent-design.md`.

### Core Components

```
User Input → LLM → Tool Calls? → Execute Tools → Results → LLM → ...
                                    ↓
                               No more calls → Response
```

### Architecture

```
┌─────────────────────────────────────────────┐
│              SimpleAgent                     │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐ │
│  │ LLMClient│  │ Registry │  │ Executor  │ │
│  └─────────┘  └──────────┘  └───────────┘ │
└─────────────────────────────────────────────┘
              ↓                ↓
       DeepSeek API      Custom Tools / MCP
```

## License

MIT
