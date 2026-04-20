from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.adapters.provider_manager import ProviderManager
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.core.s02_tools.mcp import MCPServerManager
from backend.core.s05_skills import AgentRuntime
from backend.core.task_queue import TaskQueue


class TaskExecutorDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider_manager: ProviderManager
    mcp_manager: MCPServerManager
    agent_runtime: AgentRuntime | None = None
    task_queue: TaskQueue | None = None
    feishu_client: FeishuClient | None = None


__all__ = ["TaskExecutorDeps"]
