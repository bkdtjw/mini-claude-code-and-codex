from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PermissionLevel = Literal["readonly", "readwrite"]


def _coerce_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise ValueError(f"无法将 {value!r} 解析为整数")


class AgentTask(BaseModel):
    role: str
    task: str
    permission: PermissionLevel = "readonly"
    allowed_tools: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class SimplePlan(BaseModel):
    tasks: list[AgentTask]

    @field_validator("tasks", mode="before")
    @classmethod
    def coerce_tasks_to_list(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value

    @model_validator(mode="after")
    def ensure_tasks_present(self) -> SimplePlan:
        if not self.tasks:
            raise ValueError("tasks 至少包含一个任务")
        return self


class ResolvedStage(BaseModel):
    stage_id: int
    task_roles: list[str]

    @field_validator("stage_id", mode="before")
    @classmethod
    def coerce_stage_id(cls, value: Any) -> int:
        return _coerce_int(value)


class SubAgentResult(BaseModel):
    role: str
    stage_id: int
    output: str
    is_error: bool = False

    @field_validator("stage_id", mode="before")
    @classmethod
    def coerce_stage_id(cls, value: Any) -> int:
        return _coerce_int(value)


def resolve_stages(tasks: list[AgentTask]) -> list[ResolvedStage]:
    if not tasks:
        raise ValueError("tasks 至少包含一个任务")
    task_order = [task.role for task in tasks]
    if len(task_order) != len(set(task_order)):
        raise ValueError("tasks 中的 role 不能重复")
    known_roles = set(task_order)
    pending = {task.role: set(task.depends_on) for task in tasks}
    for task in tasks:
        if task.role in task.depends_on:
            raise ValueError(f"任务 {task.role} 不能依赖自己")
        for dependency in task.depends_on:
            if dependency not in known_roles:
                raise ValueError(f"任务 {task.role} 依赖了不存在的角色: {dependency}")
    resolved: set[str] = set()
    stages: list[ResolvedStage] = []
    stage_id = 0
    while pending:
        ready_roles = [
            role_name
            for role_name in task_order
            if role_name in pending and pending[role_name].issubset(resolved)
        ]
        if not ready_roles:
            raise ValueError("任务依赖存在循环，无法推导执行阶段")
        stages.append(ResolvedStage(stage_id=stage_id, task_roles=ready_roles))
        for role_name in ready_roles:
            resolved.add(role_name)
            pending.pop(role_name, None)
        stage_id += 1
    return stages


__all__ = [
    "AgentTask",
    "PermissionLevel",
    "ResolvedStage",
    "SimplePlan",
    "SubAgentResult",
    "resolve_stages",
]
