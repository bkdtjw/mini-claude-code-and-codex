from __future__ import annotations

from backend.core.s02_tools.registry import ToolRegistry

from .bash import create_bash_tool
from .file_read import create_read_tool
from .file_write import create_write_tool


def register_builtin_tools(registry: ToolRegistry, workspace: str) -> None:
    """一次性注册所有内置工具"""
    tools = [
        create_read_tool(workspace),
        create_write_tool(workspace),
        create_bash_tool(workspace),
    ]
    for definition, executor in tools:
        registry.register(definition, executor)


__all__ = ["register_builtin_tools"]
