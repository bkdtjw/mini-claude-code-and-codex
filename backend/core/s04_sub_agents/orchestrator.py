from __future__ import annotations

import asyncio

from backend.adapters.base import LLMAdapter
from backend.common.errors import AgentError
from backend.common.types import AgentTask, ResolvedStage, SimplePlan, SubAgentResult, ToolResult, resolve_stages
from backend.core.s02_tools import ToolRegistry

from .agent_definition import AgentDefinitionLoader
from .isolated_runner import run_isolated_agent
from .runtime_models import IsolatedAgentRun, IsolatedAgentRuntime, OrchestratorConfig


class OrchestrationError(AgentError):
    def __init__(self, message: str) -> None:
        super().__init__(code="ORCHESTRATION_ERROR", message=message)


class Orchestrator:
    """Execute a simple multi-agent plan with automatic stage resolution."""

    def __init__(
        self,
        adapter: LLMAdapter,
        parent_registry: ToolRegistry,
        config: OrchestratorConfig,
    ) -> None:
        self._runtime = IsolatedAgentRuntime(
            adapter=adapter,
            parent_registry=parent_registry,
            config=config,
        )
        self._definition_loader = AgentDefinitionLoader(config.agents_dir)

    async def execute(self, plan: SimplePlan) -> ToolResult:
        try:
            stages = resolve_stages(plan.tasks)
            task_map = {task.role: task for task in plan.tasks}
            previous_outputs: dict[str, str] = {}
            results: list[SubAgentResult] = []
            for stage in stages:
                stage_results = await self._run_stage(stage.stage_id, stage.task_roles, task_map, previous_outputs)
                results.extend(stage_results)
                for result in stage_results:
                    previous_outputs[result.role] = result.output
            return ToolResult(
                output=self._format_report(stages, results),
                is_error=any(item.is_error for item in results),
            )
        except OrchestrationError:
            raise
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        except Exception as exc:
            raise OrchestrationError(str(exc)) from exc

    async def _run_stage(
        self,
        stage_id: int,
        task_roles: list[str],
        task_map: dict[str, AgentTask],
        previous_outputs: dict[str, str],
    ) -> list[SubAgentResult]:
        stage_tasks = [
            run_isolated_agent(self._build_run(task_map[role_name], previous_outputs), self._runtime)
            for role_name in task_roles
        ]
        stage_results = await asyncio.gather(*stage_tasks, return_exceptions=True)
        return [
            self._coerce_result(stage_id, role_name, result)
            for role_name, result in zip(task_roles, stage_results, strict=True)
        ]

    def _build_run(self, task: AgentTask, previous_outputs: dict[str, str]) -> IsolatedAgentRun:
        definition = self._definition_loader.load_role(task.role)
        allowed_tools = task.allowed_tools or (definition.allowed_tools if definition is not None else [])
        description = (
            definition.description
            if definition is not None and definition.description
            else f"请围绕 {task.role} 角色完成分配的子任务。"
        )
        system_prompt = definition.system_prompt if definition is not None else ""
        model = definition.model if definition is not None else ""
        max_iterations = definition.max_iterations if definition is not None else 10
        dependency_outputs = {
            role_name: previous_outputs[role_name]
            for role_name in task.depends_on
            if role_name in previous_outputs
        }
        return IsolatedAgentRun(
            task=task.model_copy(update={"allowed_tools": allowed_tools}),
            description=description,
            system_prompt=system_prompt,
            model=model,
            max_iterations=max_iterations,
            dependency_outputs=dependency_outputs,
        )

    def _coerce_result(
        self,
        stage_id: int,
        role_name: str,
        stage_result: SubAgentResult | Exception,
    ) -> SubAgentResult:
        if isinstance(stage_result, SubAgentResult):
            return stage_result.model_copy(update={"stage_id": stage_id})
        if isinstance(stage_result, AgentError):
            output = f"[{stage_result.code}] {stage_result.message}"
        else:
            output = str(stage_result)
        return SubAgentResult(role=role_name, stage_id=stage_id, output=output, is_error=True)

    def _format_report(self, stages: list[ResolvedStage], results: list[SubAgentResult]) -> str:
        error_count = sum(1 for item in results if item.is_error)
        summary = f"多 Agent 协作完成，共 {len(stages)} 个阶段，{len(results)} 个任务。"
        if error_count:
            summary = f"{summary} 其中 {error_count} 个子任务失败。"
        sections = [summary]
        for stage in stages:
            role_line = ", ".join(stage.task_roles)
            sections.append(f"\n--- 阶段 {stage.stage_id}: {role_line} ---")
            for result in (item for item in results if item.stage_id == stage.stage_id):
                status = "失败" if result.is_error else "完成"
                sections.append(f"\n[{result.role}] [{status}]")
                sections.append(result.output)
        return "\n".join(sections)


__all__ = ["Orchestrator", "OrchestrationError"]
