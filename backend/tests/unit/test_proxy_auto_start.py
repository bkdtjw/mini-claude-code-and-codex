from __future__ import annotations

from pathlib import Path

import pytest

from backend.config.settings import settings as app_settings
from backend.core.s02_tools.builtin import proxy_auto_start, proxy_tools
from backend.core.s02_tools.builtin.proxy_auto_start import AUTO_START_HINT
from backend.core.s02_tools.builtin.proxy_models import ProxyGroup, ProxyNode, ProxyStatus


class SequenceAPI:
    def __init__(self, versions: list[str]) -> None:
        self._versions = versions
        self.calls = 0

    async def get_version(self) -> str:
        index = min(self.calls, len(self._versions) - 1)
        self.calls += 1
        return self._versions[index]


class StubProcess:
    result = "v1.19.22"
    calls = 0
    configs: list[object] = []

    def __init__(self, config: object) -> None:
        self._config = config
        type(self).configs.append(config)

    async def start(self) -> str:
        type(self).calls += 1
        return type(self).result


class ToggleStatusAPI:
    def __init__(self) -> None:
        self.started = False

    async def get_proxies(self) -> ProxyStatus:
        if not self.started:
            return ProxyStatus()
        return ProxyStatus(
            groups=[ProxyGroup(name="GLOBAL", type="Selector", now="JP1", all=["JP1"])],
            nodes=[ProxyNode(name="JP1", type="Shadowsocks", alive=True, delay=42)],
        )

    async def get_version(self) -> str:
        return "v1.19.22" if self.started else ""


def _reset_runtime() -> None:
    proxy_auto_start._mihomo_api = None
    proxy_auto_start._mihomo_process = None
    StubProcess.calls = 0
    StubProcess.configs = []
    StubProcess.result = "v1.19.22"


def _clear_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "mihomo_path", "")
    monkeypatch.setattr(app_settings, "mihomo_config_path", "")
    monkeypatch.setattr(app_settings, "mihomo_work_dir", "")


@pytest.mark.asyncio
async def test_ensure_mihomo_running_api_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_runtime()
    monkeypatch.setattr(proxy_auto_start, "_get_api", lambda *_args: SequenceAPI(["v1.19.22"]))
    monkeypatch.setattr(proxy_auto_start, "MihomoProcess", StubProcess)
    assert await proxy_auto_start._ensure_mihomo_running() is None
    assert StubProcess.calls == 0


@pytest.mark.asyncio
async def test_ensure_mihomo_running_auto_start_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_runtime()
    _clear_settings(monkeypatch)
    mihomo_path = Path("tests/.tmp_proxy_auto/mihomo.exe").resolve()
    config_path = Path("tests/.tmp_proxy_auto/config.yaml").resolve()
    monkeypatch.setattr(proxy_auto_start, "_get_api", lambda *_args: SequenceAPI([""]))
    monkeypatch.setattr(proxy_auto_start, "MihomoProcess", StubProcess)
    monkeypatch.setenv("MIHOMO_PATH", str(mihomo_path))
    monkeypatch.setenv("MIHOMO_CONFIG_PATH", str(config_path))
    assert await proxy_auto_start._ensure_mihomo_running() is None
    assert StubProcess.calls == 1
    assert str(StubProcess.configs[0].work_dir) == str(mihomo_path.parent)


@pytest.mark.asyncio
async def test_ensure_mihomo_running_no_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_runtime()
    _clear_settings(monkeypatch)
    monkeypatch.setattr(proxy_auto_start, "_get_api", lambda *_args: SequenceAPI([""]))
    monkeypatch.delenv("MIHOMO_PATH", raising=False)
    monkeypatch.delenv("MIHOMO_CONFIG_PATH", raising=False)
    assert await proxy_auto_start._ensure_mihomo_running() == AUTO_START_HINT


@pytest.mark.asyncio
async def test_ensure_mihomo_running_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_runtime()
    _clear_settings(monkeypatch)
    StubProcess.result = "mihomo start timeout"
    monkeypatch.setattr(proxy_auto_start, "_get_api", lambda *_args: SequenceAPI([""]))
    monkeypatch.setattr(proxy_auto_start, "MihomoProcess", StubProcess)
    mihomo_path = Path("tests/.tmp_proxy_auto/mihomo.exe").resolve()
    config_path = Path("tests/.tmp_proxy_auto/config.yaml").resolve()
    monkeypatch.setenv("MIHOMO_PATH", str(mihomo_path))
    monkeypatch.setenv("MIHOMO_CONFIG_PATH", str(config_path))
    result = await proxy_auto_start._ensure_mihomo_running()
    assert result == "mihomo auto-start failed: mihomo start timeout"


@pytest.mark.asyncio
async def test_proxy_status_tool_auto_starts_mihomo(monkeypatch: pytest.MonkeyPatch) -> None:
    api = ToggleStatusAPI()

    async def _ensure_started(*_args: object) -> str | None:
        api.started = True
        return None

    monkeypatch.setattr(proxy_tools, "_ensure_mihomo_running", _ensure_started)
    monkeypatch.setattr(proxy_tools, "_get_api", lambda *_args: api)
    _, execute = proxy_tools.create_proxy_status_tool()
    result = await execute({})
    assert result.is_error is False
    assert "mihomo v1.19.22" in result.output
    assert "JP1(42ms)" in result.output
