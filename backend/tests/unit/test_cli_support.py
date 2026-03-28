from __future__ import annotations

from collections.abc import AsyncIterator
import json
from pathlib import Path
import tempfile
from uuid import uuid4

import pytest

from backend.adapters.base import LLMAdapter
from backend.adapters.provider_manager import ProviderManager
from backend.cli_support import (
    CliArgs,
    CliCommand,
    CliPrinter,
    create_session,
    handle_command,
    parse_args,
)
from backend.common.types import LLMRequest, LLMResponse, ProviderConfig, ProviderType, StreamChunk
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


def _provider() -> ProviderConfig:
    return ProviderConfig(
        id="provider-1",
        name="Test Provider",
        provider_type=ProviderType.OPENAI_COMPAT,
        base_url="https://example.com",
        api_key="",
        default_model="test-model",
        is_default=True,
    )


def _make_workspace() -> str:
    root = Path(__file__).resolve().parents[1] / ".tmp_cli"
    root.mkdir(exist_ok=True)
    return tempfile.mkdtemp(dir=root)


def _make_empty_mcp_manager() -> MCPServerManager:
    root = Path(__file__).resolve().parents[1] / ".tmp_cli_mcp"
    root.mkdir(exist_ok=True)
    config_path = root / f"{uuid4().hex}.json"
    config_path.write_text(json.dumps({"servers": []}), encoding="utf-8")
    return MCPServerManager(config_path=str(config_path))


def test_parse_args_supports_permission_mode() -> None:
    args = parse_args(["--workspace", ".", "--permission-mode", "readonly", "--model", "mini"])
    assert args.permission_mode == "readonly"
    assert args.model == "mini"
    assert args.workspace


@pytest.mark.asyncio
async def test_create_session_uses_default_provider_model_and_tools() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_provider()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    tool_names = [tool.name for tool in session.registry.list_definitions()]
    assert session.state.model == "test-model"
    assert session.state.provider_id == "provider-1"
    assert tool_names == ["Read", "Write", "Bash", "dispatch_agent"]


@pytest.mark.asyncio
async def test_handle_command_switches_model_and_rebuilds_session() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_provider()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    await session.loop.run("hello")
    result = await handle_command(
        session,
        CliCommand(name="/model", argument="new-model"),
        CliPrinter(),
    )
    assert result.session.state.model == "new-model"
    assert result.session.loop.messages == []


@pytest.mark.asyncio
async def test_handle_command_clear_resets_existing_history() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_provider()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    await session.loop.run("hello")
    assert session.loop.messages
    result = await handle_command(session, CliCommand(name="/clear"), CliPrinter())
    assert result.session.loop.messages == []


@pytest.mark.asyncio
async def test_handle_command_switches_workspace() -> None:
    workspace = _make_workspace()
    new_workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_provider()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    result = await handle_command(
        session,
        CliCommand(name="/workspace", argument=new_workspace),
        CliPrinter(),
    )
    assert result.session.state.workspace == new_workspace
