from __future__ import annotations

import asyncio
import platform
import re
import shlex
import subprocess

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

DANGEROUS_PATTERNS = [r"\brm\s+-rf\s+/($|\s)", r"\bmkfs(\.|$|\s)", r"(^|\s)dd(\s|$)"]
DAEMON_PATTERNS = [r"^mihomo(?:\.exe)?$"]
DAEMON_SAFE_PREFIXES = {
    "cat",
    "command",
    "file",
    "find",
    "grep",
    "head",
    "kill",
    "killall",
    "ls",
    "pgrep",
    "pkill",
    "ps",
    "stat",
    "tail",
    "taskkill",
    "tasklist",
    "type",
    "wc",
    "where",
    "which",
}
DAEMON_LAUNCH_WRAPPERS = {"env", "nice", "nohup", "setsid", "sudo", "time"}
DAEMON_REJECTION_MESSAGE = "不要用 Bash 启动 mihomo，请使用 proxy_on 工具。"
ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def _is_dangerous(command: str) -> bool:
    normalized = command.strip().lower()
    patterns = [*DANGEROUS_PATTERNS]
    if platform.system() == "Windows":
        patterns.extend([r"\bformat\s+[a-z]:", r"\brd\s+/s\s+/q\s+[a-z]:\\?$"])
    return any(re.search(pattern, normalized) for pattern in patterns)


def _split_command_tokens(command: str) -> list[str]:
    first_segment = re.split(r"\s*(?:\|\||&&|[|;])\s*", command, maxsplit=1)[0].strip()
    if not first_segment:
        return []
    try:
        return shlex.split(first_segment, posix=platform.system() != "Windows")
    except ValueError:
        return first_segment.split()


def _normalize_token(token: str) -> str:
    stripped = token.strip().strip("\"'")
    return stripped.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1].lower()


def _nested_shell_command(tokens: list[str]) -> str:
    first_token = _normalize_token(tokens[0]) if tokens else ""
    if first_token in {"bash", "sh"} and "-c" in tokens:
        index = tokens.index("-c")
        return tokens[index + 1] if index + 1 < len(tokens) else ""
    if first_token in {"cmd", "cmd.exe"}:
        for switch in ("/c", "/k"):
            if switch in tokens:
                index = tokens.index(switch)
                return tokens[index + 1] if index + 1 < len(tokens) else ""
    return ""


def _resolve_exec_token(tokens: list[str]) -> str:
    index = 0
    while index < len(tokens):
        current = _normalize_token(tokens[index])
        if current in DAEMON_LAUNCH_WRAPPERS:
            index += 1
            if current == "env":
                while index < len(tokens) and ENV_ASSIGNMENT_PATTERN.match(tokens[index]):
                    index += 1
            continue
        return tokens[index]
    return ""


def _is_daemon_launch(command: str) -> str:
    tokens = _split_command_tokens(command)
    if not tokens:
        return ""
    first_token = _normalize_token(tokens[0])
    if first_token in DAEMON_SAFE_PREFIXES:
        return ""
    nested_command = _nested_shell_command(tokens)
    if nested_command:
        return _is_daemon_launch(nested_command)
    executable = _resolve_exec_token(tokens)
    normalized_exec = _normalize_token(executable)
    if any(re.search(pattern, normalized_exec) for pattern in DAEMON_PATTERNS):
        return DAEMON_REJECTION_MESSAGE
    return ""


def _decode_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def create_bash_tool(cwd: str, timeout: int = 30) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="Bash",
        description="Execute a shell command and return the output.",
        category="shell",
        parameters=ToolParameterSchema(
            properties={"command": {"type": "string", "description": "Shell command to execute"}},
            required=["command"],
        ),
    )
    is_windows = platform.system() == "Windows"

    def run_command(command: str) -> ToolResult:
        try:
            args = ["cmd.exe", "/c", f"chcp 65001 >nul && {command}"] if is_windows else ["/bin/sh", "-c", command]
            completed = subprocess.run(
                args,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=float(timeout),
                check=False,
            )
            stdout_text = _decode_output(completed.stdout).strip()
            stderr_text = _decode_output(completed.stderr).strip()
            output = "\n".join(part for part in [stdout_text, stderr_text] if part)
            return ToolResult(output=output or f"Exit code: {completed.returncode}", is_error=completed.returncode != 0)
        except subprocess.TimeoutExpired:
            return ToolResult(output="Command timed out", is_error=True)
        except PermissionError as exc:
            return ToolResult(
                output=(
                    "Unable to start shell command.\n"
                    f"command: {command}\n"
                    f"cwd: {cwd}\n"
                    f"error: {exc}\n"
                    "The current runtime may block backend child processes, so the Bash tool is unavailable."
                ),
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            command = str(args.get("command", "")).strip()
            if not command:
                return ToolResult(output="Missing command", is_error=True)
            if _is_dangerous(command):
                return ToolResult(output="Dangerous command rejected", is_error=True)
            daemon_hint = _is_daemon_launch(command)
            if daemon_hint:
                return ToolResult(output=daemon_hint, is_error=True)
            return await asyncio.to_thread(run_command, command)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
