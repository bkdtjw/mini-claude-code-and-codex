from __future__ import annotations

import re

from backend.common.errors import AgentError
from backend.common.types import ToolResult
from backend.core.s02_tools import ToolRegistry

from .runtime_models import IsolatedRegistryConfig

READONLY_BLOCKED_PATTERNS: list[str] = [
    r"\brm(\s|$)",
    r"\bmv\s",
    r"\bcp\s",
    r"\bchmod\s",
    r"\bchown\s",
    r"\bmkdir\s",
    r"\brmdir(\s|$)",
    r"\bsed\s+-i",
    r"\btee(\s|$)",
    r"(^|[^|])>(?![>&])",
    r">>",
    r"\bpatch(\s|$)",
    r"\bcopy(\s|$)",
    r"\bmove(\s|$)",
    r"\bren(\s|$)",
    r"\bdel(\s|$)",
    r"\berase(\s|$)",
    r"\bmd(\s|$)",
    r"\brd(\s|$)",
    r"\bformat(\s|$)",
    r"\b(remove-item|set-content|add-content|new-item|move-item|copy-item|rename-item|clear-content|out-file)\b",
    r"\bgit\s+(commit|push|merge|rebase|checkout|reset|clean)\b",
    r"\bnpm\s+(install|uninstall|publish)\b",
    r"\bpip\s+(install|uninstall)\b",
]
READONLY_BLOCKED_PREFIXES = {
    "bash",
    "cmd",
    "cmd.exe",
    "cscript",
    "node",
    "node.exe",
    "perl",
    "php",
    "powershell",
    "powershell.exe",
    "py",
    "py.exe",
    "python",
    "python3",
    "python.exe",
    "pwsh",
    "pwsh.exe",
    "ruby",
    "sh",
    "wscript",
}
RECURSIVE_TOOL_NAMES = {"dispatch_agent", "orchestrate_agents"}
DEFAULT_READONLY_TOOLS = {"Read", "Bash"}
DEFAULT_READWRITE_TOOLS = {"Read", "Write", "Bash"}


class PermissionPolicyError(AgentError):
    def __init__(self, message: str) -> None:
        super().__init__(code="SUB_AGENT_PERMISSION_ERROR", message=message)


def _extract_command_prefix(command: str) -> str:
    match = re.match(r"^\s*([a-z0-9_.-]+)", command.strip().lower())
    return match.group(1) if match else ""


def is_readonly_blocked(command: str) -> bool:
    """Return whether a readonly Bash command attempts a write operation."""

    normalized = command.strip().lower()
    if not normalized:
        return True
    if any(re.search(pattern, normalized) for pattern in READONLY_BLOCKED_PATTERNS):
        return True
    return _extract_command_prefix(normalized) in READONLY_BLOCKED_PREFIXES


def _resolve_allowed_tools(config: IsolatedRegistryConfig) -> set[str]:
    if config.allowed_tool_names:
        return set(config.allowed_tool_names) - RECURSIVE_TOOL_NAMES
    if config.permission_level == "readonly":
        return set(DEFAULT_READONLY_TOOLS)
    return set(DEFAULT_READWRITE_TOOLS)


def build_isolated_registry(
    parent_registry: ToolRegistry,
    config: IsolatedRegistryConfig,
) -> ToolRegistry:
    """Build a filtered registry for a sub-agent execution."""

    _ = config.workspace
    child_registry = ToolRegistry()
    allowed = _resolve_allowed_tools(config)
    for definition in parent_registry.list_definitions():
        if definition.name in RECURSIVE_TOOL_NAMES:
            continue
        if definition.name not in allowed:
            continue
        registered = parent_registry.get(definition.name)
        if registered is None:
            continue
        _, executor = registered
        if config.permission_level == "readonly" and definition.name == "Write":
            continue
        if config.permission_level == "readonly" and definition.name == "Bash":
            original_executor = executor

            async def readonly_bash(
                args: dict[str, object],
                _exec=original_executor,
            ) -> ToolResult:
                try:
                    command = str(args.get("command", "")).strip()
                    if is_readonly_blocked(command):
                        raise PermissionPolicyError(f"readonly 模式下不允许执行修改命令: {command}")
                    return await _exec(args)
                except PermissionPolicyError as exc:
                    return ToolResult(output=f"权限拒绝: {exc.message}", is_error=True)
                except Exception as exc:
                    error = PermissionPolicyError(f"只读命令执行失败: {exc}")
                    return ToolResult(output=error.message, is_error=True)

            child_registry.register(definition, readonly_bash)
            continue
        child_registry.register(definition, executor)
    return child_registry


__all__ = [
    "PermissionPolicyError",
    "build_isolated_registry",
    "is_readonly_blocked",
    "READONLY_BLOCKED_PATTERNS",
]
