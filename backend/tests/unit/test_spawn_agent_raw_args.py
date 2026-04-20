from __future__ import annotations

import json

import pytest

from backend.core.task_queue import TaskStatus
from backend.tests.unit.test_spawn_agent import FakeQueue, _tool


@pytest.mark.asyncio
async def test_spawn_agent_accepts_raw_wrapped_json_arguments() -> None:
    queue = FakeQueue([(TaskStatus.SUCCEEDED, "done")])
    execute = _tool(queue)

    result = await execute(
        {
            "raw": json.dumps(
                {"tasks": [{"spec_id": "code-reviewer", "input": "review runtime"}]},
                ensure_ascii=False,
            )
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 1
    assert queue.submitted[0]["input_data"]["spec_id"] == "code-reviewer"
