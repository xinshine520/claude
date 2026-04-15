"""Simple Agent SDK - A simple multi-turn agent with OpenAI/DeepSeek and tool calling."""

from simple_agent.types import (
    Message,
    MessageRole,
    MessageContent,
    TextContent,
    ToolCallContent,
    ToolResultContent,
    Tool,
    ToolResult,
    Session,
    SessionStatus,
    AgentConfig,
    AgentEvent,
    AgentEventType,
)
from simple_agent.llm.client import LLMClient
from simple_agent.tool.registry import ToolRegistry
from simple_agent.tool.executor import ToolExecutor, ExecutionContext
from simple_agent.agent import Agent, SimpleAgent
from simple_agent.mcp.client import MCPClient, MCPToolAdapter, MCPConfig
from simple_agent.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
)

__version__ = "0.1.0"

__all__ = [
    # Types
    "Message",
    "MessageRole",
    "MessageContent",
    "TextContent",
    "ToolCallContent",
    "ToolResultContent",
    "Tool",
    "ToolResult",
    "Session",
    "SessionStatus",
    "AgentConfig",
    "AgentEvent",
    "AgentEventType",
    # Core
    "LLMClient",
    "ToolRegistry",
    "ToolExecutor",
    "ExecutionContext",
    "Agent",
    "SimpleAgent",
    # MCP
    "MCPClient",
    "MCPToolAdapter",
    "MCPConfig",
    # Config
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
]
