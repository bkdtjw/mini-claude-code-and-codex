from __future__ import annotations

import os
from typing import Literal

from backend.adapters.base import LLMAdapter
from backend.core.s02_tools.registry import ToolRegistry
from backend.core.s04_sub_agents import AgentDefinitionLoader, SubAgentLifecycle, SubAgentSpawner

from .bash import create_bash_tool
from .dispatch_agent import create_dispatch_agent_tool
from .feishu_notify import create_feishu_notify_tool
from .file_read import create_read_tool
from .file_write import create_write_tool

PermissionMode = Literal["readonly", "auto", "full"]


def register_builtin_tools(
    registry: ToolRegistry,
    workspace: str | None,
    mode: PermissionMode = "auto",
    adapter: LLMAdapter | None = None,
    default_model: str = "",
    agents_dir: str | None = None,
    feishu_webhook_url: str | None = None,
    feishu_secret: str | None = None,
) -> None:
    """根据权限模式注册不同的工具集。"""
    tools = [create_read_tool(workspace)] if workspace else []

    if workspace and mode in ("auto", "full"):
        tools.append(create_write_tool(workspace))
        tools.append(create_bash_tool(workspace))
        if adapter is not None:
            loader = AgentDefinitionLoader(agents_dir)
            spawner = SubAgentSpawner(adapter, registry, loader, default_model)
            lifecycle = SubAgentLifecycle(timeout=120.0)
            tools.append(create_dispatch_agent_tool(spawner, lifecycle))

    feishu_url = feishu_webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")
    resolved_feishu_secret = feishu_secret or os.environ.get("FEISHU_WEBHOOK_SECRET", "")
    if feishu_url:
        tools.append(create_feishu_notify_tool(feishu_url, resolved_feishu_secret or None))

    for definition, executor in tools:
        registry.register(definition, executor)


__all__ = ["register_builtin_tools", "PermissionMode"]
