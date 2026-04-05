from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml

from backend.core.s02_tools.builtin import proxy_manage_tools, proxy_subscription, proxy_tools
from backend.core.s02_tools.builtin.proxy_config import ProxyConfigGenerator
from backend.core.s02_tools.builtin.proxy_models import ProxyGroup, ProxyNode, ProxyStatus
from backend.core.s02_tools.builtin.proxy_tool_support import fuzzy_match


async def _fake_ensure_ok(*_args: object) -> str | None:
    return None


def test_inject_smux_adds_config_to_all_proxies() -> None:
    source = [{"name": "JP1", "type": "ss"}, {"name": "HK2", "type": "vmess"}]
    result = ProxyConfigGenerator.inject_smux(source)
    assert all(proxy["smux"]["enabled"] is True for proxy in result)
    assert result[0]["smux"]["protocol"] == "h2mux"
    assert "smux" not in source[0]


def test_inject_smux_skips_existing_and_special_proxy_types() -> None:
    source = [
        {"name": "JP1", "type": "ss", "smux": {"enabled": True, "protocol": "smux"}},
        {"name": "DIRECT", "type": "direct"},
        {"name": "REJECT", "type": "reject"},
        {"name": "HK2", "type": "vmess"},
    ]
    result = ProxyConfigGenerator.inject_smux(source)
    assert result[0]["smux"] == {"enabled": True, "protocol": "smux"}
    assert "smux" not in result[1] and "smux" not in result[2]
    assert result[3]["smux"]["enabled"] is True


def test_remove_smux_clears_all() -> None:
    source = [{"name": "JP1", "type": "ss", "smux": {"enabled": True}}]
    result = ProxyConfigGenerator.remove_smux(source)
    assert "smux" not in result[0]
    assert "smux" in source[0]


def test_default_configs_contain_required_fields() -> None:
    dns_config = ProxyConfigGenerator.default_dns_config()
    assert dns_config["enhanced-mode"] == "fake-ip"
    assert dns_config["proxy-server-nameserver"]
    doh_servers = [
        server for server in dns_config["proxy-server-nameserver"] if server.startswith("https://")
    ]
    assert len(doh_servers) >= 2
    assert ProxyConfigGenerator.default_global_opts()["external-controller"] == "127.0.0.1:9090"


def test_generate_from_subscription_creates_complete_config() -> None:
    generator = ProxyConfigGenerator(str(_make_temp_dir() / "config.yaml"))
    result = generator.generate_from_subscription(
        {"proxies": [{"name": "JP1", "type": "ss"}]},
        smux_config={"protocol": "h2mux", "brutal_up": 50, "brutal_down": 100},
        dns_config=ProxyConfigGenerator.default_dns_config(),
        global_opts=ProxyConfigGenerator.default_global_opts(),
    )
    assert result["proxy-groups"][0]["name"] == "GLOBAL"
    assert result["rules"] == ["MATCH,GLOBAL"]
    assert result["proxies"][0]["smux"]["enabled"] is True


def test_generate_config_preserves_utf8_yaml() -> None:
    generator = ProxyConfigGenerator(str(_make_temp_dir() / "config.yaml"), backup=False)
    result = generator.generate_from_subscription(
        {"proxies": [{"name": "JP1", "type": "ss"}, {"name": "HK2", "type": "vmess"}]},
        dns_config=ProxyConfigGenerator.default_dns_config(),
        global_opts=ProxyConfigGenerator.default_global_opts(),
    )
    output_path = _make_temp_dir() / "generated.yaml"
    output_path.write_text(
        yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    content = output_path.read_bytes().decode("utf-8")
    assert "JP1" in content and "HK2" in content


@pytest.mark.parametrize(
    ("keyword", "candidates", "expected"),
    [
        ("HK2", ["HK1", "HK2", "JP1"], ["HK2"]),
        ("JP", ["HK1", "JP1", "JP2", "US1"], ["JP1", "JP2"]),
        ("us", ["US1", "US2", "HK1"], ["US1", "US2"]),
        ("KR", ["HK1", "JP1"], []),
    ],
)
def test_fuzzy_match(keyword: str, candidates: list[str], expected: list[str]) -> None:
    assert fuzzy_match(keyword, candidates) == expected


def test_fetch_subscription_decodes_base64_and_plain_yaml() -> None:
    encoded = "cHJveGllczoKICAtIG5hbWU6ICJKUDEiCiAgICB0eXBlOiBzcwo="
    assert "JP1" in proxy_subscription.decode_subscription(encoded)
    plain = 'proxies:\n  - name: "JP1"\n    type: ss\n'
    assert proxy_subscription.decode_subscription(plain) == plain.strip()


class StubSwitchAPI:
    def __init__(self) -> None:
        self.switched_to = ""

    async def get_version(self) -> str:
        return "v1.19.22"

    async def get_proxies(self) -> ProxyStatus:
        return ProxyStatus(
            groups=[
                ProxyGroup(name="GLOBAL", type="Selector", now="HK1", all=["HK1", "JP1", "JP2"])
            ],
            nodes=[
                ProxyNode(name="JP1", type="ss", delay=78),
                ProxyNode(name="JP2", type="ss", delay=120),
            ],
        )

    async def switch_proxy(self, group_name: str, node_name: str) -> bool:
        self.switched_to = node_name
        return True

    async def get_delay(self, node_name: str, timeout: int = 5000, test_url: str = "") -> int:
        return 78 if node_name == "JP1" else 120


@pytest.mark.asyncio
async def test_proxy_switch_tool_with_fuzzy_match(monkeypatch: pytest.MonkeyPatch) -> None:
    api = StubSwitchAPI()
    monkeypatch.setattr(proxy_manage_tools, "_ensure_mihomo_running", _fake_ensure_ok)
    monkeypatch.setattr(proxy_manage_tools, "_get_api", lambda *_args: api)
    _, execute = proxy_tools.create_proxy_switch_tool()
    result = await execute({"node": "JP"})
    assert result.is_error is False
    assert api.switched_to == "JP1"
    assert "Matched keyword: JP" in result.output


class StubOptimizeAPI:
    async def reload_config(self, config_path: str) -> bool:
        return bool(config_path)


async def _fake_load_subscription(_url: str) -> dict[str, Any]:
    return {"proxies": [{"name": "JP1", "type": "ss"}, {"name": "HK2", "type": "vmess"}]}


@pytest.mark.asyncio
async def test_proxy_optimize_tool_import_action_defaults_to_no_smux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _make_temp_dir() / "config.yaml"
    monkeypatch.setattr(proxy_manage_tools, "_ensure_mihomo_running", _fake_ensure_ok)
    monkeypatch.setattr(proxy_manage_tools, "_get_api", lambda *_args: StubOptimizeAPI())
    monkeypatch.setattr(proxy_manage_tools, "load_subscription", _fake_load_subscription)
    _, execute = proxy_tools.create_proxy_optimize_tool(str(config_path))
    result = await execute({"action": "import", "subscription_url": "https://example.com/sub"})
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert result.is_error is False
    assert "Subscription imported" in result.output
    assert "smux not injected" in result.output
    assert all("smux" not in proxy for proxy in saved["proxies"])


def _make_temp_dir() -> Path:
    path = Path("tests/.tmp_proxy") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path
