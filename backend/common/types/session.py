from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .message import Message, generate_id

SessionStatus = Literal["idle", "running", "paused", "completed", "error"]


class SessionConfig(BaseModel):
    model: str
    provider: str = "anthropic"
    system_prompt: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7


class Session(BaseModel):
    id: str = Field(default_factory=generate_id)
    config: SessionConfig
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime
    status: SessionStatus = "idle"


__all__ = [
    "SessionStatus",
    "SessionConfig",
    "Session",
]
