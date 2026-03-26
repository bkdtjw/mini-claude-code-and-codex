from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import pytest

from backend.core.s02_tools.builtin.bash import create_bash_tool


@pytest.mark.asyncio
async def test_bash_tool_uses_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    workspace = str(Path.cwd())

    def fake_run(
        args: list[str],
        *,
        cwd: str,
        stdout: int,
        stderr: int,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        calls["args"] = args
        calls["cwd"] = cwd
        calls["stdout"] = stdout
        calls["stderr"] = stderr
        calls["timeout"] = timeout
        calls["check"] = check
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"ok\n", stderr=b"")

    _, execute = create_bash_tool(workspace)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = await execute({"command": "dir" if platform.system() == "Windows" else "ls"})

    assert result.is_error is False
    assert result.output == "ok"
    assert calls["cwd"] == workspace
    assert calls["check"] is False
    assert calls["timeout"] == 30.0
    assert calls["args"][0] == ("cmd.exe" if platform.system() == "Windows" else "/bin/sh")


@pytest.mark.asyncio
async def test_bash_tool_timeout_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = str(Path.cwd())

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd="cmd.exe", timeout=30)

    _, execute = create_bash_tool(workspace)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = await execute({"command": "dir" if platform.system() == "Windows" else "ls"})

    assert result.is_error is True
    assert result.output == "Command timed out"
