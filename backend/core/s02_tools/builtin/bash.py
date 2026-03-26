from __future__ import annotations

import asyncio
import platform
import re
import subprocess

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

DANGEROUS_PATTERNS = [r"\brm\s+-rf\s+/($|\s)", r"\bmkfs(\.|$|\s)", r"(^|\s)dd(\s|$)"]


def _is_dangerous(command: str) -> bool:
    normalized = command.strip().lower()
    patterns = [*DANGEROUS_PATTERNS]
    if platform.system() == "Windows":
        patterns.extend([r"\bformat\s+[a-z]:", r"\brd\s+/s\s+/q\s+[a-z]:\\?$"])
    return any(re.search(pattern, normalized) for pattern in patterns)


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
            return await asyncio.to_thread(run_command, command)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
