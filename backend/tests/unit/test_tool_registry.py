from __future__ import annotations

import pytest

from backend.common.errors import ToolError
from backend.common.types import ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s02_tools.registry import ToolRegistry


async def _dummy_executor(_: dict[str, object]) -> ToolResult:
    return ToolResult(tool_call_id="call_1", output="ok")


def _make_definition(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} description",
        category="shell",
        parameters=ToolParameterSchema(),
    )


def test_register_success() -> None:
    registry = ToolRegistry()
    definition = _make_definition("run_shell")
    registry.register(definition, _dummy_executor)
    found = registry.get("run_shell")
    assert found is not None
    found_definition, found_executor = found
    assert found_definition.name == "run_shell"
    assert found_executor is _dummy_executor


def test_register_duplicate_raises_error() -> None:
    registry = ToolRegistry()
    definition = _make_definition("run_shell")
    registry.register(definition, _dummy_executor)
    with pytest.raises(ToolError):
        registry.register(definition, _dummy_executor)


def test_get_not_found_returns_none() -> None:
    registry = ToolRegistry()
    assert registry.get("missing") is None


def test_list_definitions_returns_all() -> None:
    registry = ToolRegistry()
    first = _make_definition("run_shell")
    second = _make_definition("read_file")
    registry.register(first, _dummy_executor)
    registry.register(second, _dummy_executor)
    definitions = registry.list_definitions()
    assert len(definitions) == 2
    assert {item.name for item in definitions} == {"run_shell", "read_file"}
