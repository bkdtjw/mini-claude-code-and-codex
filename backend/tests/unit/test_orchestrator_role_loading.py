from __future__ import annotations

import pytest

from backend.common.types import SimplePlan
from backend.core.s02_tools import ToolRegistry
from backend.core.s04_sub_agents import Orchestrator

from .sub_agent_test_support import (
    ScenarioAdapter,
    build_orchestrator_config,
    build_task,
    make_local_temp_dir,
    register_tool,
)


@pytest.mark.asyncio
async def test_orchestrator_uses_agent_definition_loader_for_role_settings() -> None:
    agents_dir = make_local_temp_dir("agents")
    role_dir = agents_dir / "custom"
    role_dir.mkdir()
    (role_dir / "agent.md").write_text(
        "\n".join(
            [
                "---",
                "name: custom",
                "description: 自定义角色",
                "allowed_tools: [Read]",
                "max_iterations: 3",
                "model: role-model",
                "---",
                "这是一个来自 agents 目录的自定义提示词。",
            ]
        ),
        encoding="utf-8",
    )

    registry = ToolRegistry()
    register_tool(registry, "Read")
    register_tool(registry, "Bash")
    adapter = ScenarioAdapter(lambda _message: "完成")
    plan = SimplePlan(tasks=[build_task("custom", "执行")])

    result = await Orchestrator(
        adapter=adapter,
        parent_registry=registry,
        config=build_orchestrator_config(agents_dir=str(agents_dir)),
    ).execute(plan)

    assert result.is_error is False
    assert adapter.requests[0].model == "role-model"
    assert "这是一个来自 agents 目录的自定义提示词" in adapter.requests[0].messages[0].content
    assert [tool.name for tool in adapter.requests[0].tools or []] == ["Read"]
