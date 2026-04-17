from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from backend.core.s02_tools.builtin.bash import _is_daemon_launch, create_bash_tool


def test_create_bash_tool_keeps_30_second_timeout_default() -> None:
    timeout = inspect.signature(create_bash_tool).parameters["timeout"].default
    assert timeout == 30


def test_bash_tool_rejects_mihomo_launch() -> None:
    workspace = str(Path.cwd())
    _, execute = create_bash_tool(workspace)

    result = asyncio.run(
        execute({"command": "mihomo -d /tmp/mihomo -f /tmp/mihomo/config.yaml"})
    )

    assert result.is_error is True
    assert result.output == "不要用 Bash 启动 mihomo，请使用 proxy_on 工具。"


@pytest.mark.parametrize(
    "command",
    [
        "mihomo -d /tmp/mihomo -f /tmp/mihomo/config.yaml",
        "nohup /usr/local/bin/mihomo -d /tmp/mihomo -f /tmp/mihomo/config.yaml",
        "bash -c 'mihomo -d /tmp/mihomo -f /tmp/mihomo/config.yaml'",
    ],
)
def test_is_daemon_launch_rejects_mihomo_startup(command: str) -> None:
    assert _is_daemon_launch(command) == "不要用 Bash 启动 mihomo，请使用 proxy_on 工具。"


@pytest.mark.parametrize(
    "command",
    [
        "grep mihomo config.yaml",
        "ps aux | grep mihomo",
        "pkill mihomo",
        "cat mihomo.log",
        "echo mihomo",
    ],
)
def test_is_daemon_launch_allows_query_commands(command: str) -> None:
    assert _is_daemon_launch(command) == ""
