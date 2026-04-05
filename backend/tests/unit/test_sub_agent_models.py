from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.common.types import (
    AgentTask,
    ResolvedStage,
    SimplePlan,
    SubAgentResult,
    resolve_stages,
)


def test_simple_plan_accepts_single_task_dict() -> None:
    plan = SimplePlan.model_validate(
        {"tasks": {"role": "reviewer", "task": "review code"}}
    )

    assert plan.tasks == [AgentTask(role="reviewer", task="review code")]


def test_resolve_stages_groups_parallel_and_serial_tasks() -> None:
    stages = resolve_stages(
        [
            AgentTask(role="reviewer", task="review code"),
            AgentTask(role="researcher", task="collect context"),
            AgentTask(role="fixer", task="apply fix", depends_on=["reviewer"]),
            AgentTask(
                role="verifier",
                task="verify result",
                depends_on=["fixer", "researcher"],
            ),
        ]
    )

    assert stages == [
        ResolvedStage(stage_id=0, task_roles=["reviewer", "researcher"]),
        ResolvedStage(stage_id=1, task_roles=["fixer"]),
        ResolvedStage(stage_id=2, task_roles=["verifier"]),
    ]


def test_sub_agent_result_accepts_numeric_string_stage_id() -> None:
    result = SubAgentResult.model_validate(
        {"role": "reviewer", "stage_id": "1", "output": "done"}
    )
    stage = ResolvedStage.model_validate({"stage_id": "0", "task_roles": ["reviewer"]})

    assert result.stage_id == 1
    assert stage.stage_id == 0


def test_resolve_stages_rejects_unknown_or_cyclic_dependencies() -> None:
    with pytest.raises(ValueError):
        resolve_stages([AgentTask(role="fixer", task="run", depends_on=["missing"])])
    with pytest.raises(ValueError):
        resolve_stages(
            [
                AgentTask(role="a", task="run", depends_on=["b"]),
                AgentTask(role="b", task="run", depends_on=["a"]),
            ]
        )


def test_simple_plan_rejects_empty_tasks() -> None:
    with pytest.raises(ValidationError):
        SimplePlan.model_validate({"tasks": []})
