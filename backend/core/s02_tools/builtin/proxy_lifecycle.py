from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

from .proxy_api import MihomoAPI
from .proxy_chain import ChainProxyManager
from .proxy_config import ProxyConfigGenerator
from .proxy_custom_nodes import CustomNodesManager
from .proxy_models import ProxyConfig, ProxyLifecycleConfig
from .proxy_process import MihomoProcess
from .proxy_subscription import parse_subscription_yaml

INTERNET_SETTINGS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37


class ProxyLifecycleError(Exception):
    """Raised when proxy lifecycle operations fail."""


class ProxyLifecycle:
    """Manage mihomo startup, shutdown, and system proxy settings."""

    def __init__(self, config: ProxyLifecycleConfig) -> None:
        self._config = config

    async def start(self, force: bool = True) -> str:
        try:
            self._kill_process(Path(self._config.mihomo_path).name)
            generator = ProxyConfigGenerator(self._config.config_path)
            config = (
                generator.load()
                if not force and Path(self._config.config_path).exists()
                else self._build_config(generator)
            )
            merged = CustomNodesManager(self._config.custom_nodes_path).merge_into_config(config)
            generator.save(merged)
            version = await MihomoProcess(_process_config(self._config)).start()
            if not version.startswith("v"):
                raise ProxyLifecycleError(version)
            proxy_set = self.set_system_proxy("127.0.0.1", self._config.proxy_port)
            exit_nodes = CustomNodesManager(self._config.custom_nodes_path).get_exit_nodes()
            chains = ChainProxyManager.list_chains(merged)
            first_exit = exit_nodes[0]["name"] if exit_nodes else "无"
            return "\n".join(
                [
                    "代理已启动",
                    f"mihomo: {version}",
                    f"代理端口: 127.0.0.1:{self._config.proxy_port}",
                    f"系统代理: {'已设置' if proxy_set else '设置失败'}",
                    f"节点数: {len(merged.get('proxies') or [])}",
                    f"落地节点: {first_exit}",
                    f"链式节点: {len(chains)} 个",
                ]
            )
        except Exception as exc:  # noqa: BLE001
            raise ProxyLifecycleError(f"开启代理失败: {exc}") from exc

    async def stop(self) -> str:
        try:
            cleared = self.clear_system_proxy()
            self._kill_process(Path(self._config.mihomo_path).name)
            return "\n".join(["代理已关闭", f"系统代理: {'已还原' if cleared else '还原失败'}"])
        except Exception as exc:  # noqa: BLE001
            raise ProxyLifecycleError(f"关闭代理失败: {exc}") from exc

    async def status(self) -> str:
        try:
            version = await MihomoAPI(self._config.api_url, self._config.api_secret).get_version()
            chain_config = CustomNodesManager(self._config.custom_nodes_path).get_chain_config()
            return "\n".join(
                [
                    f"mihomo: {version or '未运行'}",
                    f"系统代理: {'已设置' if self.is_system_proxy_set() else '未设置'}",
                    f"链式出口: {chain_config.get('exit_node') or '无'}",
                ]
            )
        except Exception as exc:  # noqa: BLE001
            raise ProxyLifecycleError(f"查询代理状态失败: {exc}") from exc

    @staticmethod
    def set_system_proxy(host: str, port: int) -> bool:
        try:
            _set_proxy_values({"ProxyEnable": 1, "ProxyServer": f"{host}:{port}"})
            return True
        except Exception:
            return False

    @staticmethod
    def clear_system_proxy() -> bool:
        try:
            _set_proxy_values({"ProxyEnable": 0})
            return True
        except Exception:
            return False

    @staticmethod
    def is_system_proxy_set() -> bool:
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY) as key:
                value, _ = winreg.QueryValueEx(key, "ProxyEnable")
            return bool(value)
        except Exception:
            return False

    @staticmethod
    def _kill_process(exe_name: str) -> None:
        result = subprocess.run(
            ["taskkill", "/f", "/im", exe_name],
            check=False,
            capture_output=True,
            text=True,
        )
        stderr = (result.stderr or "").lower()
        if result.returncode and "not found" not in stderr and "没有运行的任务" not in stderr:
            raise ProxyLifecycleError(f"结束 mihomo 进程失败: {result.stderr or result.stdout}")

    def _build_config(self, generator: ProxyConfigGenerator) -> dict[str, object]:
        raw = Path(self._config.sub_path).read_text(encoding="utf-8")
        subscription = parse_subscription_yaml(raw)
        return generator.generate_from_subscription(
            subscription,
            smux_config=None,
            dns_config=ProxyConfigGenerator.default_dns_config(),
            global_opts=ProxyConfigGenerator.default_global_opts(),
        )


def _process_config(config: ProxyLifecycleConfig) -> ProxyConfig:
    return ProxyConfig(
        mihomo_path=config.mihomo_path,
        config_path=config.config_path,
        work_dir=config.work_dir,
        api_url=config.api_url,
        api_secret=config.api_secret,
    )


def _set_proxy_values(values: dict[str, int | str]) -> None:
    if winreg is None:
        raise ProxyLifecycleError("当前平台不支持系统代理设置")
    access = getattr(winreg, "KEY_SET_VALUE", 0) | getattr(winreg, "KEY_QUERY_VALUE", 0)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_KEY, 0, access) as key:
        for name, value in values.items():
            value_type = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, value_type, value)
    ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
    ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)


__all__ = ["ProxyLifecycle", "ProxyLifecycleError"]
