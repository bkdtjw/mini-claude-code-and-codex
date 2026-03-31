from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system", "tool"]


def generate_id() -> str:
    return uuid4().hex[:12]


class ToolCall(BaseModel):
    id: str = Field(default_factory=generate_id)
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    tool_call_id: str = Field(default_factory=generate_id)
    output: str
    is_error: bool = False


class Message(BaseModel):
    id: str = Field(default_factory=generate_id)
    role: Role
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class StreamChunk(BaseModel):
    type: Literal["text", "tool_call", "tool_result", "done"]
    data: Any = None


__all__ = [
    "Role",
    "ToolCall",
    "ToolResult",
    "Message",
    "StreamChunk",
    "generate_id",
]
