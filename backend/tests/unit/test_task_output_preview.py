from __future__ import annotations

from backend.core.s07_task_system.output_preview import (
    build_task_output_preview,
    render_task_output_preview,
)


def test_short_output_renders_as_original_text() -> None:
    preview = build_task_output_preview("done")

    assert render_task_output_preview(preview) == "done"


def test_truncated_output_includes_ref_and_counts() -> None:
    preview = build_task_output_preview("abcdef", content_ref="reports/task.md", limit=3)

    rendered = render_task_output_preview(preview)

    assert "完整输出: reports/task.md" in rendered
    assert "已截断: 显示前 3 / 6 字符" in rendered
    assert rendered.endswith("abc")
