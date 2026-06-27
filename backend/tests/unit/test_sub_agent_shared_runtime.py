from __future__ import annotations

from pathlib import Path

from backend.core.s04_sub_agents import (
    AgentOutputArtifactRequest,
    AgentResultV1,
    DependencyInputRequest,
    ToolScopeRequest,
    build_dependency_input,
    resolve_task_tools,
    sink_large_agent_output,
)


def _result(summary: str) -> AgentResultV1:
    return AgentResultV1(status="passed", summary=summary)


def test_context_isolation() -> None:
    text = build_dependency_input(
        DependencyInputRequest(
            task_input="设计测试",
            depends_on=["runtime_audit"],
            dependency_results={
                "runtime_audit": _result("runtime ok"),
                "security_audit": _result("secret finding"),
            },
        )
    )

    assert "设计测试" in text
    assert "runtime_audit" in text
    assert "runtime ok" in text
    assert "security_audit" not in text
    assert "secret finding" not in text


def test_artifact_by_reference(tmp_path: Path) -> None:
    large_output = "x" * 120
    result = AgentResultV1(status="warning", summary="large output", raw_output=large_output)

    sunk = sink_large_agent_output(
        AgentOutputArtifactRequest(
            result=result,
            raw_output=large_output,
            artifacts_dir=str(tmp_path),
            session_id="run-1",
            artifact_name="report",
            max_inline_chars=20,
        )
    )

    assert sunk.artifact_path
    assert Path(sunk.artifact_path).is_absolute()
    assert Path(sunk.artifact_path).exists()
    assert large_output in Path(sunk.artifact_path).read_text(encoding="utf-8")
    assert sunk.result.artifacts == [sunk.artifact_path]
    assert sunk.result.extra["raw_output_artifact_path"] == sunk.artifact_path
    assert sunk.result.raw_output is None
    assert large_output not in sunk.content
    assert "read_history mode=full json_path=.raw" in sunk.content


def test_tool_scope_matches_declaration() -> None:
    readonly_tools = resolve_task_tools(
        ToolScopeRequest(tools=["Read", "Write", "Bash", "str_replace"], permission="readonly")
    )
    writable_tools = resolve_task_tools(
        ToolScopeRequest(tools=["Read", "Write"], permission="writable")
    )

    assert readonly_tools == ["Read"]
    assert writable_tools == ["Read", "Write"]
