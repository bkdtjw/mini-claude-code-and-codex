from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible request payload."""

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[dict[str, Any]] | None = None
    provider_id: str | None = None
    workspace: str | None = None
    permission_mode: str = "auto"


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: dict[str, Any]
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible response payload."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


__all__ = [
    "ChatCompletionRequest",
    "ChatCompletionChoice",
    "ChatCompletionUsage",
    "ChatCompletionResponse",
]
