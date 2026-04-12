from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.config.settings import settings as app_settings
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import (
    proxy_chain_tools,
    proxy_lifecycle_tools,
    register_builtin_tools,
)
from backend.core.s02_tools.builtin.proxy_chain import EXIT_PREFIX
from backend.core.s02_tools.builtin.proxy_chain_tools import create_proxy_chain_tool
from backend.core.s02_tools.builtin.proxy_lifecycle_tools import (
    create_proxy_off_tool,
    create_proxy_on_tool,
)

from .proxy_chain_test_support import FakeChainAPI, write_config
from .proxy_lifecycle_test_support import make_base_config, make_runtime_config


@pytest.mark.asyncio
async def test_proxy_on_and_off_tool_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_runtime_config()

    class DummyLifecycle:
        async def start(self, force: bool = True) -> str:
            return f"start:{force}"

        async def stop(self) -> str:
            return "stop"

    monkeypatch.setattr(proxy_lifecycle_tools, "_get_lifecycle", lambda *_args: DummyLifecycle())
    on_def, on_execute = create_proxy_on_tool(
        mihomo_path=config.mihomo_path,
        config_path=config.config_path,
        work_dir=config.work_dir,
        sub_path=config.sub_path,
        custom_nodes_path=config.custom_nodes_path,
        api_url=config.api_url,
        secret=config.api_secret,
    )
    off_def, off_execute = create_proxy_off_tool()
    on_result = await on_execute({"force": False})
    off_result = await off_execute({})
    assert on_def.name == "proxy_on"
    assert on_result.output == "start:False"
    assert off_def.name == "proxy_off"
    assert off_result.output == "stop"


def test_register_builtin_tools_adds_proxy_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_runtime_config()
    monkeypatch.setattr(app_settings, "mihomo_path", config.mihomo_path)
    monkeypatch.setattr(app_settings, "mihomo_config_path", config.config_path)
    monkeypatch.setattr(app_settings, "mihomo_work_dir", config.work_dir)
    monkeypatch.setattr(app_settings, "mihomo_sub_path", config.sub_path)
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=None, mode="readonly")
    assert registry.has("proxy_on")
    assert registry.has("proxy_off")


@pytest.mark.asyncio
async def test_proxy_chain_syncs_to_custom_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_runtime_config()

    async def _ensure_ok(*_args: object) -> None:
        return None

    write_config(Path(config.config_path), make_base_config())
    api = FakeChainAPI()
    monkeypatch.setattr(proxy_chain_tools, "_get_api", lambda *_args: api)
    monkeypatch.setattr(proxy_chain_tools, "_ensure_mihomo_running", _ensure_ok)
    _, execute = create_proxy_chain_tool(
        config.config_path, custom_nodes_path=config.custom_nodes_path
    )
    add_result = await execute(
        {
            "action": "add_exit",
            "name": "relay",
            "type": "http",
            "server": "na-relay.oneproxy.vip",
            "port": 1337,
            "extra": {"username": "demo"},
        }
    )
    set_result = await execute({"action": "set", "exit_node": "relay", "transit_pattern": "HK"})
    data = yaml.safe_load(Path(config.custom_nodes_path).read_text(encoding="utf-8"))
    assert add_result.is_error is False
    assert set_result.is_error is False
    assert data["exit_nodes"][0]["name"] == f"{EXIT_PREFIX}relay"
    assert data["chain_config"]["exit_node"] == f"{EXIT_PREFIX}relay"
    assert data["chain_config"]["transit_pattern"] == "HK"
