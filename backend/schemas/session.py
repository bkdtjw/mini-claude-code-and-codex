from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    model: str
    provider_id: str | None = None
    system_prompt: str = ""
    workspace: str | None = None


class UpdateSessionTitleRequest(BaseModel):
    title: str


class SessionResponse(BaseModel):
    id: str
    config: dict[str, Any]
    status: str
    created_at: str
    message_count: int


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse] = Field(default_factory=list)


__all__ = [
    "CreateSessionRequest",
    "UpdateSessionTitleRequest",
    "SessionResponse",
    "SessionListResponse",
]
