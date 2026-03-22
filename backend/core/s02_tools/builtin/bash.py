from __future__ import annotations

import asyncio
import re
import shlex

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult


def _is_dangerous(command: str) -> bool:
    normalized = command.strip().lower()
    patterns = [r"\brm\s+-rf\s+/($|\s)", r"\bmkfs(\.|$|\s)", r"(^|\s)dd(\s|$)"]
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

    async def execute(args: dict[str, object]) -> ToolResult:
        command = str(args.get("command", "")).strip()
        if not command:
            return ToolResult(output="Missing command", is_error=True)
        if _is_dangerous(command):
            return ToolResult(output="Dangerous command rejected", is_error=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                *shlex.split(command),
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(output="Command timed out", is_error=True)
            output = "\n".join(
                part
                for part in [stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()]
                if part
            )
            return ToolResult(output=output or f"Exit code: {proc.returncode}", is_error=proc.returncode != 0)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
