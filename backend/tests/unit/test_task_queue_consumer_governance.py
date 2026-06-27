from __future__ import annotations

from types import SimpleNamespace

from backend.api.task_queue_consumer_governance import (
    apply_child_loop_budget,
    enforce_child_loop_permission,
)
from backend.common.types import ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s02_tools.executor import ToolExecutor
from backend.core.s02_tools.registry import ToolRegistry


class FakeExecutor:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def list_definitions(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in self._names]

    def remove(self, name: str) -> None:
        self._names = [item for item in self._names if item != name]


def test_enforce_child_loop_permission_removes_write_tools() -> None:
    loop = SimpleNamespace(
        _executor=FakeExecutor(["Read", "Write", "Bash", "Edit", "Grep"]),
        _config=SimpleNamespace(tools=["Read", "Write", "Bash", "Edit", "Grep"]),
    )

    enforce_child_loop_permission(loop, {"permission": "readonly"})

    assert loop._config.tools == ["Grep", "Read"]  # noqa: SLF001


def test_enforce_child_loop_permission_keeps_writable_tools() -> None:
    loop = SimpleNamespace(
        _executor=FakeExecutor(["Read", "Write", "Bash"]),
        _config=SimpleNamespace(tools=["Read", "Write", "Bash"]),
    )

    enforce_child_loop_permission(loop, {"permission": "writable"})

    assert loop._config.tools == ["Read", "Write", "Bash"]  # noqa: SLF001


def test_enforce_child_loop_permission_removes_tools_from_real_executor() -> None:
    registry = ToolRegistry()
    for name in ["Read", "Write", "Bash"]:
        registry.register(
            ToolDefinition(name=name, description=name, category="file-ops", parameters=ToolParameterSchema()),
            _noop_tool,
        )
    loop = SimpleNamespace(
        _executor=ToolExecutor(registry),
        _config=SimpleNamespace(tools=["Read", "Write", "Bash"]),
    )

    enforce_child_loop_permission(loop, {"permission": "readonly"})

    assert loop._config.tools == ["Read"]  # noqa: SLF001
    assert registry.get("Write") is None
    assert registry.get("Bash") is None


def test_apply_child_loop_budget_sets_max_iterations() -> None:
    loop = SimpleNamespace(_config=SimpleNamespace(max_iterations=20))

    apply_child_loop_budget(loop, {"max_iterations": 37})

    assert loop._config.max_iterations == 37  # noqa: SLF001


def test_apply_child_loop_budget_clamps_worker_side_cap() -> None:
    loop = SimpleNamespace(_config=SimpleNamespace(max_iterations=20))

    apply_child_loop_budget(loop, {"max_iterations": 100, "max_iterations_cap": 12})

    assert loop._config.max_iterations == 12  # noqa: SLF001


def test_apply_child_loop_budget_does_not_trust_payload_cap() -> None:
    loop = SimpleNamespace(_config=SimpleNamespace(max_iterations=20))

    apply_child_loop_budget(loop, {"max_iterations": 9999, "max_iterations_cap": 9999})

    assert loop._config.max_iterations == 60  # noqa: SLF001


def test_apply_child_loop_budget_uses_worker_default_cap_when_missing() -> None:
    loop = SimpleNamespace(_config=SimpleNamespace(max_iterations=20))

    apply_child_loop_budget(loop, {"max_iterations": 999})

    assert loop._config.max_iterations == 60  # noqa: SLF001


async def _noop_tool(_: dict[str, object]) -> ToolResult:
    return ToolResult(output="ok")
