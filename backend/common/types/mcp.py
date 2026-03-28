from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.common.utils import generate_id


class MCPServerConfig(BaseModel):
    id: str = Field(default_factory=generate_id)
    name: str
    transport: Literal["stdio", "sse"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    enabled: bool = True


class MCPToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    server_id: str


class MCPToolResult(BaseModel):
    content: str
    is_error: bool = False


class MCPServerStatus(BaseModel):
    id: str
    name: str
    transport: str
    connected: bool
    tool_count: int = 0
    enabled: bool = True


__all__ = [
    "MCPServerConfig",
    "MCPServerStatus",
    "MCPToolInfo",
    "MCPToolResult",
]
