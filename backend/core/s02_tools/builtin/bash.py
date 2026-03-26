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
def create_bash_tool(cwd: str, timeout: int = 30) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="Bash",
        description="执行 shell 命令并返回输出",
        category="shell",
        parameters=ToolParameterSchema(
            properties={"command": {"type": "string", "description": "要执行的命令"}},
            required=["command"],
        ),
    )
    is_windows = platform.system() == "Windows"

    async def execute(args: dict[str, object]) -> ToolResult:
        command = str(args.get("command", "")).strip()
        if not command:
            return ToolResult(output="Missing command", is_error=True)
        if _is_dangerous(command):
            return ToolResult(output="Dangerous command rejected", is_error=True)
        try:
            if is_windows:
                proc = await asyncio.create_subprocess_exec(
                    "cmd.exe",
                    "/c",
                    f"chcp 65001 >nul && {command}",
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/sh",
                    "-c",
                    command,
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(output="Command timed out", is_error=True)

            def decode_output(data: bytes) -> str:
                if not data:
                    return ""
                for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
                    try:
                        return data.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return data.decode("utf-8", errors="replace")

            stdout_text = decode_output(stdout_bytes).strip()
            stderr_text = decode_output(stderr_bytes).strip()
            output = "\n".join(part for part in [stdout_text, stderr_text] if part)
            return ToolResult(output=output or f"Exit code: {proc.returncode}", is_error=proc.returncode != 0)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
