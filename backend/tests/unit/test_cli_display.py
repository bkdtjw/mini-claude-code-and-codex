from __future__ import annotations

import json
import re
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from backend.adapters.base import LLMAdapter
from backend.adapters.provider_manager import ProviderManager
from backend.cli_support import CliArgs, CliCommand, CliPrinter, create_session, handle_command
from backend.common.types import (
    AgentEvent,
    LLMRequest,
    LLMResponse,
    ProviderConfig,
    ProviderType,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    ToolParameterSchema,
    ToolResult,
)
from backend.core.s02_tools.mcp import MCPServerManager


class FakeAdapter(LLMAdapter):
    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=f"echo: {request.messages[-1].content}")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


class FakeProviderManager(ProviderManager):
    def __init__(self, provider: ProviderConfig) -> None:
        self._provider = provider
        self._adapter = FakeAdapter()

    async def list_all(self) -> list[ProviderConfig]:
        return [self._provider]

    async def get_adapter(self, provider_id: str | None = None) -> LLMAdapter:
        return self._adapter


def _provider(model: str = "kimi-k2-thinking") -> ProviderConfig:
    return ProviderConfig(
        id="provider-1",
        name="Test Provider",
        provider_type=ProviderType.OPENAI_COMPAT,
        base_url="https://example.com",
        api_key="",
        default_model=model,
        available_models=[model],
        is_default=True,
    )


def _make_workspace() -> str:
    root = Path(__file__).resolve().parents[1] / ".tmp_cli_display"
    root.mkdir(exist_ok=True)
    return tempfile.mkdtemp(dir=root)


def _make_empty_mcp_manager() -> MCPServerManager:
    root = Path(__file__).resolve().parents[1] / ".tmp_cli_display_mcp"
    root.mkdir(exist_ok=True)
    config_path = root / f"{uuid4().hex}.json"
    config_path.write_text(json.dumps({"servers": []}), encoding="utf-8")
    return MCPServerManager(config_path=str(config_path))


async def _noop_tool(_: dict[str, object]) -> ToolResult:
    return ToolResult(output="ok")


def _register_tool(session_name: str, session: object) -> None:
    registry = getattr(session, "registry")
    registry.register(
        ToolDefinition(
            name=session_name,
            description="test",
            category="mcp" if session_name.startswith("mcp__") else "code-analysis",
            parameters=ToolParameterSchema(),
        ),
        _noop_tool,
    )


@pytest.mark.asyncio
async def test_print_welcome_groups_tools_and_shows_provider_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = await create_session(
        CliArgs(workspace=_make_workspace()),
        manager=FakeProviderManager(_provider()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    session.state.workspace = "C:/Users/nirvana/Desktop/projects/very/deep/repo/agent-studio"
    for name in [
        "mcp__git__status",
        "mcp__git__diff",
        "mcp__github__create_issue",
        "mcp__github__create_pull_request",
        "mcp__github__search_code",
        "mcp__github__search_repositories",
        "mcp__github__get_file_contents",
        "mcp__github__list_pull_requests",
    ]:
        _register_tool(name, session)
    CliPrinter().print_welcome(session)
    output = capsys.readouterr().out
    assert "miniclaude v0.1.0" in output
    assert "workspace: .../repo/agent-studio" in output
    assert "thinking: auto" in output
    assert "/provider <name>" in output
    assert "builtin" in output
    assert "github" in output
    assert "(+3)" in output


@pytest.mark.asyncio
async def test_tools_command_prints_grouped_tools(capsys: pytest.CaptureFixture[str]) -> None:
    session = await create_session(
        CliArgs(workspace=_make_workspace()),
        manager=FakeProviderManager(_provider("test-model")),
        mcp_manager=_make_empty_mcp_manager(),
    )
    for name in ["mcp__git__status", "mcp__git__diff", "mcp__github__create_issue"]:
        _register_tool(name, session)
    await handle_command(session, CliCommand(name="/tools"), CliPrinter())
    output = capsys.readouterr().out
    assert "tools (" in output
    assert "builtin" in output
    assert "git" in output
    assert "github" in output


def test_printer_formats_tool_events(capsys: pytest.CaptureFixture[str]) -> None:
    printer = CliPrinter()
    started_at = datetime(2026, 3, 28, 10, 0, 0)
    output = "\n".join(f"line {index}" for index in range(12))
    printer.handle_event(
        AgentEvent(
            type="tool_call",
            data=ToolCall(id="call-1", name="Bash", arguments={"command": "ls"}),
            timestamp=started_at,
        )
    )
    printer.handle_event(
        AgentEvent(
            type="tool_result",
            data=ToolResult(tool_call_id="call-1", output=output),
            timestamp=started_at + timedelta(seconds=0.3),
        )
    )
    formatted = capsys.readouterr().out
    assert "[OK]" in formatted or "✓" in formatted
    assert "Bash(ls)" in formatted
    assert re.search(r"\(\d+\.\ds\)", formatted)
    assert "28800" not in formatted
    assert ">>" not in formatted
    assert "ok 完成" not in formatted
