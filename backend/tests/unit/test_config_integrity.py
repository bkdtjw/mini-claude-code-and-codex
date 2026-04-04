from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml

from backend.core.s02_tools.builtin import proxy_chain_tools, proxy_manage_tools
from backend.core.s02_tools.builtin.proxy_chain import EXIT_PREFIX, ChainProxyManager
from backend.core.s02_tools.builtin.proxy_config import ConfigError, ProxyConfigGenerator
from backend.core.s02_tools.builtin.proxy_tools import (
    create_proxy_chain_tool,
    create_proxy_optimize_tool,
)


async def _fake_ensure_ok(*_args: object) -> str | None:
    return None


class ReloadRecorder:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def reload_config(self, config_path: str) -> bool:
        self.paths.append(config_path)
        return True


async def _fake_load_subscription(_url: str) -> dict[str, Any]:
    return {"proxies": [{"name": "JP1", "type": "ss"}, {"name": "HK1", "type": "vmess"}]}


def test_save_verify_catches_missing_proxies_and_restores_backup() -> None:
    path = _make_temp_path("config.yaml")
    generator = ProxyConfigGenerator(str(path))
    good = _base_config()
    generator.save(good)
    bad = dict(good)
    bad.pop("proxies")
    with pytest.raises(ConfigError, match="proxies"):
        generator.save(bad)
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == good


def test_save_verify_catches_missing_dns() -> None:
    generator = ProxyConfigGenerator(str(_make_temp_path("config.yaml")), backup=False)
    bad = _base_config()
    bad["dns"] = {"enhanced-mode": "fake-ip"}
    with pytest.raises(ConfigError, match="proxy-server-nameserver"):
        generator.save(bad)


def test_save_verify_catches_missing_external_controller() -> None:
    generator = ProxyConfigGenerator(str(_make_temp_path("config.yaml")), backup=False)
    bad = _base_config()
    bad.pop("external-controller")
    with pytest.raises(ConfigError, match="external-controller"):
        generator.save(bad)


def test_save_verify_passes_valid_config() -> None:
    path = _make_temp_path("config.yaml")
    generator = ProxyConfigGenerator(str(path), backup=False)
    assert generator.save(_base_config()) == str(path)


def test_add_exit_node_preserves_all_fields() -> None:
    source = _base_config()
    result = ChainProxyManager.add_exit_node(
        source,
        "relay",
        "http",
        "relay.example.com",
        1337,
        "",
        extra={"username": "demo"},
    )
    _assert_preserved_fields(source, result)


def test_set_chain_preserves_all_fields() -> None:
    source = _chain_config()
    result, _ = ChainProxyManager.set_chain(source, "出口")
    _assert_preserved_fields(source, result)


def test_remove_chain_preserves_all_fields() -> None:
    source, _ = ChainProxyManager.set_chain(_chain_config(), "出口")
    result, _ = ChainProxyManager.remove_chain(source)
    _assert_preserved_fields(source, result)


@pytest.mark.asyncio
async def test_optimize_import_defaults_to_no_smux(monkeypatch: pytest.MonkeyPatch) -> None:
    path = _make_temp_path("config.yaml")
    api = ReloadRecorder()
    monkeypatch.setattr(proxy_manage_tools, "_ensure_mihomo_running", _fake_ensure_ok)
    monkeypatch.setattr(proxy_manage_tools, "_get_api", lambda *_args: api)
    monkeypatch.setattr(proxy_manage_tools, "load_subscription", _fake_load_subscription)
    _, execute = create_proxy_optimize_tool(str(path))
    result = await execute({"action": "import", "subscription_url": "https://example.com/sub"})
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert result.is_error is False
    assert all("smux" not in proxy for proxy in data["proxies"])


@pytest.mark.asyncio
async def test_reload_uses_absolute_path(monkeypatch: pytest.MonkeyPatch) -> None:
    optimize_path = _make_temp_path("optimize.yaml")
    chain_path = _make_temp_path("chain.yaml")
    optimize_api = ReloadRecorder()
    chain_api = ReloadRecorder()
    monkeypatch.setattr(proxy_manage_tools, "_ensure_mihomo_running", _fake_ensure_ok)
    monkeypatch.setattr(proxy_manage_tools, "_get_api", lambda *_args: optimize_api)
    monkeypatch.setattr(proxy_manage_tools, "load_subscription", _fake_load_subscription)
    monkeypatch.setattr(proxy_chain_tools, "_ensure_mihomo_running", _fake_ensure_ok)
    monkeypatch.setattr(proxy_chain_tools, "_get_api", lambda *_args: chain_api)
    chain_path.write_text(
        yaml.safe_dump(_chain_config(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _, optimize_execute = create_proxy_optimize_tool(str(optimize_path))
    _, chain_execute = create_proxy_chain_tool(str(chain_path))
    await optimize_execute({"action": "import", "subscription_url": "https://example.com/sub"})
    await chain_execute(
        {
            "action": "add_exit",
            "name": "relay",
            "type": "http",
            "server": "r.example.com",
            "port": 80,
        }
    )
    assert Path(optimize_api.paths[-1]).is_absolute()
    assert Path(chain_api.paths[-1]).is_absolute()


def test_add_exit_node_http_with_username() -> None:
    result = ChainProxyManager.add_exit_node(
        _base_config(),
        "relay",
        "http",
        "na-relay.oneproxy.vip",
        1337,
        "",
        extra={"username": "test", "password": "", "skip-cert-verify": False},
    )
    node = next(proxy for proxy in result["proxies"] if proxy["server"] == "na-relay.oneproxy.vip")
    assert node["username"] == "test"
    assert "password" not in node
    assert "skip-cert-verify" not in node


def _base_config() -> dict[str, Any]:
    return {
        "mixed-port": 7890,
        "external-controller": "127.0.0.1:9090",
        "dns": ProxyConfigGenerator.default_dns_config(),
        "rules": ["MATCH,GLOBAL"],
        "rule-providers": {"demo": {"type": "http"}},
        "proxies": [{"name": "香港A", "type": "ss", "server": "hk.example.com", "port": 443}],
        "proxy-groups": [{"name": "GLOBAL", "type": "select", "proxies": ["香港A"]}],
    }


def _chain_config() -> dict[str, Any]:
    config = _base_config()
    config["proxies"] = [
        {"name": "香港A", "type": "ss", "server": "hk.example.com", "port": 443},
        {"name": "日本A", "type": "ss", "server": "jp.example.com", "port": 443},
        {
            "name": f"{EXIT_PREFIX}出口",
            "type": "trojan",
            "server": "us.example.com",
            "port": 443,
            "password": "pass",
        },
    ]
    config["proxy-groups"] = [
        {
            "name": "GLOBAL",
            "type": "select",
            "proxies": ["香港A", "日本A", f"{EXIT_PREFIX}出口"],
        }
    ]
    return config


def _assert_preserved_fields(source: dict[str, Any], result: dict[str, Any]) -> None:
    assert result["dns"] == source["dns"]
    assert result["rules"] == source["rules"]
    assert result["rule-providers"] == source["rule-providers"]
    assert result["mixed-port"] == source["mixed-port"]
    assert result["external-controller"] == source["external-controller"]


def _make_temp_path(filename: str) -> Path:
    path = Path("tests/.tmp_proxy_integrity") / uuid4().hex / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
