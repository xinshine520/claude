"""Core type definitions for Simple Agent SDK."""

from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """Message role types."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ContentType(str, Enum):
    """Content block types."""
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


# Content Blocks
class TextContent(BaseModel):
    """Text content block."""
    type: Literal["text"] = "text"
    text: str


class ToolCallContent(BaseModel):
    """Tool call content block."""
    type: Literal["tool_call"] = "tool_call"
    id: str = Field(description="Unique tool call ID")
    name: str = Field(description="Tool name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolResultContent(BaseModel):
    """Tool result content block."""
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str = Field(description="Corresponding tool call ID")
    result: str = Field(description="Execution result")
    is_error: bool = Field(default=False, description="Whether result is an error")


MessageContent = TextContent | ToolCallContent | ToolResultContent


# Message
class Message(BaseModel):
    """Chat message."""
    id: str = Field(default_factory=lambda: f"msg_{datetime.now().timestamp()}")
    role: MessageRole
    content: list[MessageContent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


# Tool Definitions
class Tool(BaseModel):
    """Tool definition."""
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    # Execute is set at runtime, not serialized

    class Config:
        arbitrary_types_allowed = True


class ToolDefinition(BaseModel):
    """Tool definition in OpenAI function format."""
    type: str = "function"
    function: dict[str, Any]


class ToolResult(BaseModel):
    """Tool execution result."""
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# Session
class SessionStatus(str, Enum):
    """Session status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class Session(BaseModel):
    """Agent session."""
    id: str = Field(default_factory=lambda: f"session_{datetime.now().timestamp()}")
    messages: list[Message] = Field(default_factory=list)
    system_prompt: str = ""
    model: str = "gpt-4o-mini"
    status: SessionStatus = SessionStatus.IDLE


# LLM Types
class LLMInput(BaseModel):
    """LLM input parameters."""
    model: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    system: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


class LLMOutput(BaseModel):
    """LLM output."""
    content: list[MessageContent]
    finish_reason: str
    usage: dict[str, int] = Field(default_factory=dict)


# Agent Event Types
class AgentEventType(str, Enum):
    """Agent event types."""
    MESSAGE_START = "message_start"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MESSAGE_END = "message_end"
    ERROR = "error"


class AgentEvent(BaseModel):
    """Agent event."""
    type: AgentEventType
    data: dict[str, Any] = Field(default_factory=dict)


# Agent Config
class AgentConfig(BaseModel):
    """Agent configuration."""
    model: str = "gpt-4o-mini"
    system_prompt: str = ""
    max_steps: int = 200
    temperature: float = 0.7
    max_tokens: int = 4096
