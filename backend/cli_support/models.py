from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.adapters.provider_manager import ProviderManager
from backend.common.errors import AgentError
from backend.common.types import AgentEventHandler
from backend.core.s02_tools.mcp import MCPServerManager
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry

PermissionMode = Literal["readonly", "auto", "full"]


class CliError(AgentError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message)


class CliArgs(BaseModel):
    workspace: str
    model: str | None = None
    provider: str | None = None
    permission_mode: PermissionMode = "auto"
    mcp_config: str | None = None


class CliCommand(BaseModel):
    name: str
    argument: str = ""


class SessionUpdate(BaseModel):
    model: str | None = None
    provider: str | None = None
    workspace: str | None = None
    permission_mode: PermissionMode | None = None
    preserve_history: bool = False
    clear_provider_metadata: bool = False


class CliState(BaseModel):
    provider_id: str
    provider_name: str
    model: str
    available_models: list[str] = Field(default_factory=list)
    workspace: str
    permission_mode: PermissionMode


class CliSession(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    manager: ProviderManager
    mcp_manager: MCPServerManager | None = None
    loop: AgentLoop
    registry: ToolRegistry
    state: CliState
    event_handler: AgentEventHandler | None = None


class CliCommandResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session: CliSession
    should_exit: bool = False


__all__ = [
    "CliArgs",
    "CliCommand",
    "CliCommandResult",
    "CliError",
    "CliSession",
    "CliState",
    "PermissionMode",
    "SessionUpdate",
]
