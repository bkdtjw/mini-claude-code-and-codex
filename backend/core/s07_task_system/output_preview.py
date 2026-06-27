from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_PREVIEW_CHARS = 500


class TaskOutputPreview(BaseModel):
    preview: str
    original_chars: int = Field(ge=0)
    is_truncated: bool = False
    content_ref: str = ""


def build_task_output_preview(
    content: str,
    *,
    content_ref: str = "",
    limit: int = DEFAULT_PREVIEW_CHARS,
) -> TaskOutputPreview:
    safe_limit = max(1, limit)
    preview = content if len(content) <= safe_limit else content[:safe_limit].rstrip()
    return TaskOutputPreview(
        preview=preview,
        original_chars=len(content),
        is_truncated=len(content) > safe_limit,
        content_ref=content_ref,
    )


def render_task_output_preview(preview: TaskOutputPreview) -> str:
    if not preview.is_truncated and not preview.content_ref:
        return preview.preview
    lines = ["[输出预览]"]
    if preview.content_ref:
        lines.append(f"完整输出: {preview.content_ref}")
    if preview.is_truncated:
        lines.append(
            f"已截断: 显示前 {len(preview.preview)} / {preview.original_chars} 字符"
        )
    if preview.preview:
        lines.extend(["", preview.preview])
    return "\n".join(lines)


__all__ = [
    "DEFAULT_PREVIEW_CHARS",
    "TaskOutputPreview",
    "build_task_output_preview",
    "render_task_output_preview",
]
