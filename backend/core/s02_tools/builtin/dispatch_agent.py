from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult
from backend.core.s04_sub_agents import (
    ResultAggregator,
    SpawnParams,
    SubAgentLifecycle,
    SubAgentSpawner,
)


class DispatchAgentArgs(BaseModel):
    role: str = ""
    task: str | None = None
    tasks: list[str] = Field(default_factory=list)
    context: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    model: str = ""
    max_concurrent: int = 3

    @model_validator(mode="after")
    def _validate_task_inputs(self) -> DispatchAgentArgs:
        if self.task is None and not self.tasks:
            raise ValueError("Either 'task' or 'tasks' must be provided.")
        if self.max_concurrent < 1:
            raise ValueError(
                f"'max_concurrent' must be at least 1, got {self.max_concurrent}."
            )
        return self


def create_dispatch_agent_tool(
    spawner: SubAgentSpawner,
    lifecycle: SubAgentLifecycle,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    """Create the dispatch_agent tool."""

    definition = ToolDefinition(
        name="dispatch_agent",
        description="派生一个或多个子 Agent 处理子任务；支持并行执行。",
        category="code-analysis",
        parameters=ToolParameterSchema(
            properties={
                "role": {
                    "type": "string",
                    "description": "子 Agent 角色名，如 reviewer、implementer",
                },
                "task": {"type": "string", "description": "单个子任务描述"},
                "tasks": {"type": "array", "description": "多个子任务描述（并行执行）"},
                "context": {"type": "string", "description": "额外上下文"},
                "allowed_tools": {"type": "array", "description": "覆盖角色默认工具列表"},
                "model": {"type": "string", "description": "覆盖角色默认模型"},
                "max_concurrent": {"type": "integer", "description": "并行执行数，默认 3"},
            },
            required=[],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            parsed = DispatchAgentArgs.model_validate(args)
            if parsed.tasks:
                params_list = [
                    SpawnParams(
                        role=parsed.role,
                        task=task,
                        context=parsed.context,
                        allowed_tools=parsed.allowed_tools,
                        model=parsed.model,
                    )
                    for task in parsed.tasks
                ]
                results = await ResultAggregator.run_parallel(
                    spawner, params_list, parsed.max_concurrent
                )
                return ResultAggregator.merge_results(results)
            params = SpawnParams(
                role=parsed.role,
                task=parsed.task or "",
                context=parsed.context,
                allowed_tools=parsed.allowed_tools,
                model=parsed.model,
            )
            return await lifecycle.run_with_timeout(spawner, params)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = ["create_dispatch_agent_tool"]
