from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.common.utils import generate_id

SERVER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SHELL_META_CHARS = ("&&", "||", ";", "|", ">", "<", "`")


class MCPServerConfig(BaseModel):
    id: str = Field(default_factory=generate_id)
    name: str
    transport: Literal["stdio", "sse"]
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    enabled: bool = True

    @model_validator(mode="after")
    def validate_config(self) -> "MCPServerConfig":
        if not SERVER_ID_PATTERN.fullmatch(self.id):
            raise ValueError("id must be 1-64 characters of letters, numbers, '_' or '-'.")
        if any(token in self.command for token in SHELL_META_CHARS):
            raise ValueError("command contains disallowed shell metacharacters.")
        if self.transport == "stdio" and not self.command.strip():
            raise ValueError("command is required when transport is 'stdio'.")
        if self.transport == "sse":
            url = self.url.strip()
            if not url:
                raise ValueError("url is required when transport is 'sse'.")
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError("url must start with 'http://' or 'https://'.")
        return self


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
