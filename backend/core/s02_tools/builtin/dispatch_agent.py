from __future__ import annotations

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult
from backend.core.s04_sub_agents import SpawnParams, SubAgentLifecycle, SubAgentSpawner


def create_dispatch_agent_tool(
    spawner: SubAgentSpawner,
    lifecycle: SubAgentLifecycle,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    """Create the dispatch_agent tool."""

    definition = ToolDefinition(
        name="dispatch_agent",
        description="派生一个子 Agent 处理指定子任务并返回结果。",
        category="code-analysis",
        parameters=ToolParameterSchema(
            properties={
                "role": {"type": "string", "description": "子 Agent 角色名，如 reviewer、implementer"},
                "task": {"type": "string", "description": "子任务描述"},
                "context": {"type": "string", "description": "额外上下文"},
                "allowed_tools": {"type": "array", "description": "覆盖角色默认工具列表"},
                "model": {"type": "string", "description": "覆盖角色默认模型"},
            },
            required=["task"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            params = SpawnParams.model_validate(args)
            return await lifecycle.run_with_timeout(spawner, params)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = ["create_dispatch_agent_tool"]
