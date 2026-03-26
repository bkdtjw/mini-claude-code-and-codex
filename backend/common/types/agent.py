from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Literal, TypeAlias

from pydantic import BaseModel, Field

AgentStatus = Literal[
    "idle",
    "thinking",
    "tool_calling",
    "waiting_approval",
    "done",
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
    type: Literal["status_change", "message", "tool_call", "tool_result", "error"]
    data: Any = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


AgentEventHandler: TypeAlias = Callable[[AgentEvent], Awaitable[None] | None]


__all__ = [
    "AgentStatus",
    "AgentConfig",
    "AgentEvent",
    "AgentEventHandler",
]
