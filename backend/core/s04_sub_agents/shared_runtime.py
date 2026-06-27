from __future__ import annotations

from pydantic import BaseModel, Field

from backend.core.s02_tools.builtin.spawn_agent_governance import (
    filter_tools_for_permission,
    normalize_permission,
)
from backend.core.s06_context_compression.level1_artifact import (
    ArtifactWriteRequest,
    write_artifact,
)

from .result_contract import AgentResultV1

DEFAULT_ARTIFACTS_DIR = "data/artifacts"
DEFAULT_MAX_INLINE_CHARS = 4000


class DependencyInputRequest(BaseModel):
    task_input: str
    depends_on: list[str] = Field(default_factory=list)
    dependency_results: dict[str, AgentResultV1] = Field(default_factory=dict)


class ToolScopeRequest(BaseModel):
    tools: list[str] = Field(default_factory=list)
    permission: str = "readonly"


class AgentOutputArtifactRequest(BaseModel):
    result: AgentResultV1
    raw_output: str
    artifacts_dir: str = DEFAULT_ARTIFACTS_DIR
    session_id: str = "default"
    artifact_name: str = "sub-agent-result"
    max_inline_chars: int = DEFAULT_MAX_INLINE_CHARS


class AgentOutputArtifactResult(BaseModel):
    content: str
    result: AgentResultV1
    artifact_path: str = ""


def build_dependency_input(request: DependencyInputRequest) -> str:
    parts = [request.task_input]
    for dependency_id in request.depends_on:
        dependency_result = request.dependency_results.get(dependency_id)
        if dependency_result is None:
            continue
        parts.append(
            f"[来自 {dependency_id} 的结果]\n"
            f"{dependency_result.model_dump_json(exclude={'raw_output'})}"
        )
    return "\n\n".join(part for part in parts if part.strip())


def resolve_task_tools(request: ToolScopeRequest) -> list[str]:
    return filter_tools_for_permission(
        request.tools,
        normalize_permission(request.permission),
    )


def sink_large_agent_output(request: AgentOutputArtifactRequest) -> AgentOutputArtifactResult:
    if len(request.raw_output) <= request.max_inline_chars:
        return AgentOutputArtifactResult(content=request.raw_output, result=request.result)
    path = write_artifact(
        ArtifactWriteRequest(
            output=request.raw_output,
            artifacts_dir=request.artifacts_dir,
            session_id=request.session_id,
            tool_call_id=request.artifact_name,
        )
    )
    raw_output = None if request.result.raw_output == request.raw_output else request.result.raw_output
    extra = {**request.result.extra, "raw_output_artifact_path": path}
    result = request.result.model_copy(
        update={
            "artifacts": [*request.result.artifacts, path],
            "extra": extra,
            "raw_output": raw_output,
        }
    )
    return AgentOutputArtifactResult(
        content=(
            "[子 agent 结果已归档]\n"
            f"完整结果: {path}\n"
            "读取方式: read_history mode=full json_path=.raw"
        ),
        result=result,
        artifact_path=path,
    )


__all__ = [
    "AgentOutputArtifactRequest",
    "AgentOutputArtifactResult",
    "DEFAULT_ARTIFACTS_DIR",
    "DEFAULT_MAX_INLINE_CHARS",
    "DependencyInputRequest",
    "ToolScopeRequest",
    "build_dependency_input",
    "resolve_task_tools",
    "sink_large_agent_output",
]
