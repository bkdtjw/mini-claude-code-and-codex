from __future__ import annotations

from backend.core.s02_tools.builtin.spawn_agent_support import PreparedTask, format_result
from backend.core.task_queue import TaskPayload, TaskStatus


def test_format_result_appends_sub_agent_tool_call_summary() -> None:
    prepared = [
        PreparedTask(
            index=1,
            task_id="task-1",
            label="daily-ai-news",
            timeout_seconds=60.0,
            input_data={"spec_id": "daily-ai-news"},
        )
    ]
    statuses = [
        TaskPayload(
            task_id="task-1",
            namespace="sub_agent",
            input_data={"spec_id": "daily-ai-news"},
            status=TaskStatus.SUCCEEDED,
            created_at=0.0,
            result={"content": "done", "tool_call_count": 4},
        )
    ]

    result = format_result(prepared, statuses)

    assert result.is_error is False
    assert "[meta] sub_agent_tool_calls=4" in result.output
