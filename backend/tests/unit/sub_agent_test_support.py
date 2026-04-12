from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from uuid import uuid4

from backend.adapters.base import LLMAdapter
from backend.common.types import (
    AgentTask,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    ToolDefinition,
    ToolParameterSchema,
    ToolResult,
)
from backend.core.s02_tools import ToolRegistry
from backend.core.s04_sub_agents import OrchestratorConfig


class ScenarioAdapter(LLMAdapter):
    def __init__(
        self,
        response_fn: Callable[[str], str],
        delay_fn: Callable[[str], float] | None = None,
    ) -> None:
        self._response_fn = response_fn
        self._delay_fn = delay_fn or (lambda _message: 0.0)
        self.requests: list[LLMRequest] = []
        self.max_concurrency = 0
        self._active_calls = 0

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        message = request.messages[-1].content
        self.requests.append(request)
        self._active_calls += 1
        self.max_concurrency = max(self.max_concurrency, self._active_calls)
        try:
            delay = self._delay_fn(message)
            if delay:
                await asyncio.sleep(delay)
            return LLMResponse(content=self._response_fn(message))
        finally:
            self._active_calls -= 1

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def build_task(role_name: str, task: str, permission: str = "readonly", depends_on: list[str] | None = None) -> AgentTask:
    return AgentTask(
        role=role_name,
        task=task,
        permission=permission,
        depends_on=depends_on or [],
    )


def build_orchestrator_config(
    workspace: str = "workspace",
    agents_dir: str | None = None,
    timeout: float = 120.0,
) -> OrchestratorConfig:
    return OrchestratorConfig(
        workspace=workspace,
        default_model="test-model",
        timeout_per_agent=timeout,
        agents_dir=agents_dir,
    )


def register_tool(registry: ToolRegistry, name: str) -> None:
    async def executor(args: dict[str, object]) -> ToolResult:
        return ToolResult(output=str(args))

    registry.register(
        ToolDefinition(
            name=name,
            description=f"mock {name}",
            category="code-analysis",
            parameters=ToolParameterSchema(),
        ),
        executor,
    )


def make_local_temp_dir(prefix: str) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_sub_agents"
    root.mkdir(exist_ok=True)
    path = root / f"{prefix}_{uuid4().hex}"
    path.mkdir()
    return path


__all__ = [
    "ScenarioAdapter",
    "build_task",
    "build_orchestrator_config",
    "make_local_temp_dir",
    "register_tool",
]
