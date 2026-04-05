from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentStatus = Literal[
    "idle",
    "thinking",
    "compacting",
    "tool_calling",
    "waiting_approval",
    "done",
    "error",
]

AgentEventType = Literal[
    "status_change",
    "message",
    "tool_call",
    "tool_result",
    "security_reject",
    "error",
]


class AgentConfig(BaseModel):
    model: str
    provider: str = "anthropic"
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    max_iterations: int = 20
    max_consecutive_tool_failures: int = 3


class AgentEvent(BaseModel):
    type: AgentEventType
    data: Any = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


type AgentEventHandler = Callable[[AgentEvent], Awaitable[None] | None]


__all__ = [
    "AgentStatus",
    "AgentEventType",
    "AgentConfig",
    "AgentEvent",
    "AgentEventHandler",
]
