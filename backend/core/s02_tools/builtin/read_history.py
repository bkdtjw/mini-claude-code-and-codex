from __future__ import annotations

from backend.common.types import (
    ToolDefinition,
    ToolExecuteFn,
    ToolParameterSchema,
    ToolPermission,
    ToolResult,
)

from .read_history_support import ALLOWED_ROOTS, HistoryReadRequest, read_history_content


def create_read_history_tool() -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="read_history",
        description=(
            "当压缩摘要、归档结果或历史文件中的信息不足以完成当前任务时，"
            "从历史文件中检索片段，或按 full/range 模式读取完整/分页内容。"
        ),
        category="file-ops",
        parameters=ToolParameterSchema(
            properties={
                "file_path": {
                    "type": "string",
                    "description": "历史文件路径，如 data/artifacts/.../result.json",
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词；也可传 .raw 这类 JSON path",
                },
                "mode": {
                    "type": "string",
                    "description": "search（默认）、full（读取正文）、range（分页读取）",
                },
                "offset": {"type": "integer", "description": "range/full 起始字符偏移"},
                "limit": {"type": "integer", "description": "最多返回字符数"},
                "json_path": {"type": "string", "description": "JSON path，如 .raw"},
            },
            required=["file_path"],
        ),
        permission=ToolPermission(
            requires_approval=False,
            sandboxed=True,
            allowed_paths=list(ALLOWED_ROOTS),
        ),
        side_effect=False,
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            request = HistoryReadRequest.model_validate(args)
            if not request.file_path.strip():
                return ToolResult(output="file_path is required", is_error=True)
            if request.mode == "search" and not request.query.strip():
                return ToolResult(output="query is required for search mode", is_error=True)
            return ToolResult(output=read_history_content(request))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = ["create_read_history_tool"]
