from __future__ import annotations

from collections.abc import AsyncIterator
import json
from pathlib import Path
import tempfile
from uuid import uuid4

import pytest

from backend.adapters.base import LLMAdapter
from backend.adapters.provider_manager import ProviderManager
from backend.cli_support import CliArgs, CliCommand, CliPrinter, create_session, handle_command, parse_args
from backend.common.types import LLMRequest, LLMResponse, Message, ProviderConfig, ProviderType, StreamChunk
from backend.core.s02_tools.mcp import MCPServerManager


class FakeAdapter(LLMAdapter):
    def __init__(self, label: str) -> None:
        self._label = label

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=f"{self._label}: {request.messages[-1].content}")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


class FakeProviderManager(ProviderManager):
    def __init__(self, providers: list[ProviderConfig]) -> None:
        self._providers = providers
        self._adapters = {provider.id: FakeAdapter(provider.id) for provider in providers}

    async def list_all(self) -> list[ProviderConfig]:
        return list(self._providers)

    async def get_adapter(self, provider_id: str | None = None) -> LLMAdapter:
        target_id = provider_id or next((provider.id for provider in self._providers if provider.is_default), self._providers[0].id)
        return self._adapters[target_id]


def _provider(
    provider_id: str,
    name: str,
    default_model: str,
    available_models: list[str],
    is_default: bool = False,
) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPAT,
        base_url="https://example.com",
        api_key="",
        default_model=default_model,
        available_models=available_models,
        is_default=is_default,
    )


def _providers() -> list[ProviderConfig]:
    return [
        _provider("provider-1", "Test Provider", "test-model", ["test-model", "new-model"], is_default=True),
        _provider("provider-2", "Alt Provider", "alt-model", ["alt-model"]),
    ]


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
        manager=FakeProviderManager(_providers()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    tool_names = [tool.name for tool in session.registry.list_definitions()]
    assert session.state.model == "test-model"
    assert session.state.provider_id == "provider-1"
    assert session.state.available_models == ["test-model", "new-model"]
    assert tool_names[:5] == ["Read", "Write", "Bash", "dispatch_agent", "orchestrate_agents"]


@pytest.mark.asyncio
async def test_handle_command_switches_model_and_preserves_history() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_providers()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    await session.loop.run("hello")
    result = await handle_command(session, CliCommand(name="/model", argument="new-model"), CliPrinter())
    assert result.session.state.model == "new-model"
    assert [message.role for message in result.session.loop.messages] == ["system", "user", "assistant"]


@pytest.mark.asyncio
async def test_handle_command_switches_provider_and_clears_provider_metadata() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_providers()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    session.loop._messages = [  # noqa: SLF001
        Message(role="system", content="system"),
        Message(role="assistant", content="answer", provider_metadata={"reasoning_content": "step"}),
    ]
    result = await handle_command(session, CliCommand(name="/provider", argument="Alt Provider"), CliPrinter())
    assert result.session.state.provider_id == "provider-2"
    assert result.session.state.model == "alt-model"
    assert result.session.loop.messages[1].provider_metadata == {}
    follow_up = await result.session.loop.run("ping")
    assert follow_up.content == "provider-2: ping"


@pytest.mark.asyncio
async def test_handle_command_rejects_model_from_other_provider() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_providers()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    result = await handle_command(session, CliCommand(name="/model", argument="alt-model"), CliPrinter())
    assert result.session.state.provider_id == "provider-1"
    assert result.session.state.model == "test-model"


@pytest.mark.asyncio
async def test_handle_command_clear_resets_existing_history() -> None:
    workspace = _make_workspace()
    session = await create_session(
        CliArgs(workspace=workspace),
        manager=FakeProviderManager(_providers()),
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
        manager=FakeProviderManager(_providers()),
        mcp_manager=_make_empty_mcp_manager(),
    )
    result = await handle_command(session, CliCommand(name="/workspace", argument=new_workspace), CliPrinter())
    assert result.session.state.workspace == new_workspace
