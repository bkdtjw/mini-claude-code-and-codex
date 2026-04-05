from __future__ import annotations

from pydantic import BaseModel, Field

from .message import ToolCall


class SecurityPolicy(BaseModel):
    """安全策略配置。"""

    allowed_tools: list[str] = Field(default_factory=list)
    dangerous_tools: list[str] = Field(default_factory=list)
    max_calls_per_turn: int = Field(default=10, ge=0)


class SignedToolCall(BaseModel):
    """经过 SecurityGate 签名的工具调用。"""

    tool_call: ToolCall
    sequence: int
    timestamp: float
    signature: str


__all__ = ["SecurityPolicy", "SignedToolCall"]
