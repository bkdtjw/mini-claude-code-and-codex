from __future__ import annotations

import os

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult


def _is_safe_path(path: str) -> bool:
    if not path or os.path.isabs(path):
        return False
    return ".." not in path.replace("\\", "/").split("/")


def create_write_tool(base_path: str) -> tuple[ToolDefinition, ToolExecuteFn]:
    """返回 (定义, 执行函数) 的 tuple，方便直接传给 registry.register()"""
    definition = ToolDefinition(
        name="Write",
        description="写入内容到指定路径文件",
        category="file-ops",
        parameters=ToolParameterSchema(
            properties={
                "path": {"type": "string", "description": "相对文件路径"},
                "content": {"type": "string", "description": "写入内容"},
            },
            required=["path", "content"],
        ),
    )
    root = os.path.abspath(base_path)

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            relative_path = str(args.get("path", ""))
            if not _is_safe_path(relative_path):
                return ToolResult(output="Invalid path", is_error=True)
            full_path = os.path.abspath(os.path.join(root, relative_path))
            if not full_path.startswith(root + os.sep) and full_path != root:
                return ToolResult(output="Invalid path", is_error=True)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as file:
                file.write(str(args.get("content", "")))
            return ToolResult(output=f"Wrote file: {relative_path}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
