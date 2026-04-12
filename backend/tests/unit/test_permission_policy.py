from __future__ import annotations

import pytest

from backend.common.types import ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s02_tools import ToolRegistry
from backend.core.s04_sub_agents import IsolatedRegistryConfig, build_isolated_registry, is_readonly_blocked


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"mock {name}",
        category="code-analysis",
        parameters=ToolParameterSchema(),
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "sed -i s/a/b/ file.py",
        "git commit -m test",
        "copy a b",
        "del file.txt",
        "powershell -Command Set-Content x.txt 1",
        "python -c \"open('x.txt', 'w').write('1')\"",
    ],
)
def test_is_readonly_blocked_rejects_mutating_commands(command: str) -> None:
    assert is_readonly_blocked(command) is True


@pytest.mark.parametrize("command", ["dir", "type file.py", "git status", "findstr pattern file.py"])
def test_is_readonly_blocked_allows_read_commands(command: str) -> None:
    assert is_readonly_blocked(command) is False


@pytest.mark.asyncio
async def test_build_isolated_registry_enforces_readonly_bash_policy() -> None:
    calls: list[str] = []
    registry = ToolRegistry()

    async def bash_executor(args: dict[str, object]) -> ToolResult:
        calls.append(str(args.get("command", "")))
        return ToolResult(output=f"ran:{args.get('command', '')}")

    async def write_executor(args: dict[str, object]) -> ToolResult:
        return ToolResult(output=f"wrote:{args.get('path', '')}")

    registry.register(_tool("Read"), write_executor)
    registry.register(_tool("Write"), write_executor)
    registry.register(_tool("Bash"), bash_executor)
    registry.register(_tool("dispatch_agent"), write_executor)
    registry.register(_tool("orchestrate_agents"), write_executor)

    isolated = build_isolated_registry(
        registry,
        IsolatedRegistryConfig(permission_level="readonly", allowed_tool_names=[], workspace="workspace"),
    )
    assert isolated.has("Read")
    assert isolated.has("Bash")
    assert not isolated.has("Write")
    assert not isolated.has("dispatch_agent")
    assert not isolated.has("orchestrate_agents")

    bash_tool = isolated.get("Bash")
    assert bash_tool is not None
    _, executor = bash_tool
    denied = await executor({"command": "copy a b"})
    allowed = await executor({"command": "dir"})

    assert denied.is_error is True
    assert "权限拒绝" in denied.output
    assert allowed.is_error is False
    assert allowed.output == "ran:dir"
    assert calls == ["dir"]


def test_build_isolated_registry_readwrite_keeps_default_tools() -> None:
    registry = ToolRegistry()

    async def executor(args: dict[str, object]) -> ToolResult:
        return ToolResult(output=str(args))

    registry.register(_tool("Read"), executor)
    registry.register(_tool("Write"), executor)
    registry.register(_tool("Bash"), executor)

    isolated = build_isolated_registry(
        registry,
        IsolatedRegistryConfig(permission_level="readwrite", allowed_tool_names=[], workspace="workspace"),
    )
    assert isolated.has("Read")
    assert isolated.has("Write")
    assert isolated.has("Bash")


def test_build_isolated_registry_recursive_allowlist_does_not_expand_defaults() -> None:
    registry = ToolRegistry()

    async def executor(args: dict[str, object]) -> ToolResult:
        return ToolResult(output=str(args))

    registry.register(_tool("Read"), executor)
    registry.register(_tool("Write"), executor)
    registry.register(_tool("Bash"), executor)
    registry.register(_tool("dispatch_agent"), executor)

    isolated = build_isolated_registry(
        registry,
        IsolatedRegistryConfig(
            permission_level="readonly",
            allowed_tool_names=["dispatch_agent"],
            workspace="workspace",
        ),
    )

    assert not isolated.has("Read")
    assert not isolated.has("Write")
    assert not isolated.has("Bash")
