from __future__ import annotations

import os

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .diff_support import build_unified_diff


def _is_safe_path(path: str) -> bool:
    if not path or os.path.isabs(path):
        return False
    return ".." not in path.replace("\\", "/").split("/")


def create_write_tool(base_path: str) -> tuple[ToolDefinition, ToolExecuteFn]:
    """返回 (定义, 执行函数) 的 tuple，方便直接传给 registry.register()"""
    definition = ToolDefinition(
        name="Write",
        description=(
            "写入完整文件内容。编辑已有文件时默认使用 str_replace；"
            "str_replace 无法唯一匹配时使用 file_edit。"
        ),
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
            old_exists = os.path.exists(full_path)
            old_content = ""
            if old_exists:
                try:
                    with open(full_path, encoding="utf-8") as file:
                        old_content = file.read()
                except UnicodeDecodeError:
                    old_content = ""
            new_content = str(args.get("content", ""))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as file:
                file.write(new_content)
            diff = build_unified_diff(relative_path, old_content, new_content, old_exists=old_exists)
            return ToolResult(output=f"Wrote file: {relative_path}", diffs=[diff] if diff else [])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
