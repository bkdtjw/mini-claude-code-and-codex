from __future__ import annotations

from typing import Literal

from backend.core.s02_tools.registry import ToolRegistry

from .bash import create_bash_tool
from .file_read import create_read_tool
from .file_write import create_write_tool

PermissionMode = Literal["readonly", "auto", "full"]


def register_builtin_tools(
    registry: ToolRegistry,
    workspace: str,
    mode: PermissionMode = "auto",
) -> None:
    """根据权限模式注册不同的工具集。"""
    tools = [create_read_tool(workspace)]

    if mode in ("auto", "full"):
        tools.append(create_write_tool(workspace))
        tools.append(create_bash_tool(workspace))

    for definition, executor in tools:
        registry.register(definition, executor)


__all__ = ["register_builtin_tools", "PermissionMode"]
