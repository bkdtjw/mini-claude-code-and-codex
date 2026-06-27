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


def test_format_result_inlines_structured_result_when_raw_output_is_archived() -> None:
    prepared = [
        PreparedTask(
            index=1,
            task_id="task-1",
            label="tech-research",
            timeout_seconds=60.0,
            input_data={"spec_id": "tech-research"},
        )
    ]
    statuses = [
        TaskPayload(
            task_id="task-1",
            namespace="sub_agent",
            input_data={"spec_id": "tech-research"},
            status=TaskStatus.SUCCEEDED,
            created_at=0.0,
            result={
                "content": "[子 agent 结果已归档]\n完整结果: data/artifacts/task/result.json",
                "agent_result": {
                    "status": "passed",
                    "summary": "字节 AI Agent 调研完成",
                    "findings": [
                        {
                            "severity": "P1",
                            "title": "企业知识库是主要场景",
                            "evidence": ["WebSearch result"],
                            "recommendation": "继续核验来源",
                        }
                    ],
                    "next_steps": ["汇总三家公司横向对比"],
                },
            },
        )
    ]

    result = format_result(prepared, statuses)

    assert "字节 AI Agent 调研完成" in result.output
    assert "企业知识库是主要场景" in result.output
    assert "完整结果: data/artifacts/task/result.json" in result.output
    assert "read_history" in result.output
