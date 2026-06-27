from __future__ import annotations

import inspect
from typing import Any

from backend.adapters.base import LLMAdapter
from backend.core.s02_tools.builtin.spawn_agent_governance import (
    is_write_tool_name,
    normalize_permission,
)
from backend.core.s04_sub_agents import (
    AgentOutputArtifactRequest,
    coerce_agent_result,
    sink_large_agent_output,
)

DEFAULT_CHILD_MAX_ITERATIONS_CAP = 60


def enforce_child_loop_permission(loop: Any, input_data: dict[str, object]) -> None:
    permission = normalize_permission(str(input_data.get("permission", "readonly")))
    if permission != "readonly":
        return
    registry = getattr(loop, "_executor", None)
    if registry is None:
        return
    list_definitions = getattr(registry, "list_definitions", None)
    remove_tool = getattr(registry, "remove", None)
    if not callable(list_definitions) or not callable(remove_tool):
        return
    definitions = list_definitions()
    if inspect.isawaitable(definitions):
        close = getattr(definitions, "close", None)
        if callable(close):
            close()
        return
    for tool in definitions:
        if is_write_tool_name(tool.name):
            remove_tool(tool.name)
    config = getattr(loop, "_config", None)
    if config is not None and hasattr(config, "tools"):
        config.tools = sorted(tool.name for tool in list_definitions())


def apply_child_loop_budget(loop: Any, input_data: dict[str, object]) -> None:
    config = getattr(loop, "_config", None)
    if config is None or not hasattr(config, "max_iterations"):
        return
    value = input_data.get("max_iterations")
    if value in {None, ""}:
        return
    try:
        payload_cap = int(input_data.get("max_iterations_cap", DEFAULT_CHILD_MAX_ITERATIONS_CAP))
        cap = min(max(1, payload_cap), DEFAULT_CHILD_MAX_ITERATIONS_CAP)
        config.max_iterations = max(1, min(int(value), max(1, cap)))
    except (TypeError, ValueError):
        return


async def build_sub_agent_complete_result(loop: Any, result: Any) -> dict[str, object]:
    content = getattr(result, "content", "") or str(result)
    adapter = getattr(loop, "_adapter", None)
    if not isinstance(adapter, LLMAdapter):
        adapter = None
    model_value = getattr(getattr(loop, "_config", None), "model", "")
    model = model_value if isinstance(model_value, str) else ""
    contract = await coerce_agent_result(str(content), adapter=adapter, model=model)
    session_id = str(getattr(getattr(loop, "_config", None), "session_id", "")) or "default"
    artifact = sink_large_agent_output(
        AgentOutputArtifactRequest(result=contract, raw_output=str(content), session_id=session_id)
    )
    return {"content": artifact.content, "agent_result": artifact.result.model_dump(mode="json")}


__all__ = [
    "apply_child_loop_budget",
    "build_sub_agent_complete_result",
    "enforce_child_loop_permission",
]
