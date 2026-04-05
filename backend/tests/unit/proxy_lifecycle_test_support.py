from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import yaml

from backend.core.s02_tools.builtin.proxy_chain import EXIT_PREFIX
from backend.core.s02_tools.builtin.proxy_models import ProxyLifecycleConfig


def make_lifecycle_paths() -> dict[str, Path]:
    root = Path(__file__).resolve().parents[1] / ".tmp_proxy_lifecycle" / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "root": root,
        "mihomo": root / "mihomo.exe",
        "config": root / "config.yaml",
        "sub": root / "sub_raw.yaml",
        "custom": root / "custom_nodes.yaml",
    }
    paths["mihomo"].write_text("exe", encoding="utf-8")
    paths["sub"].write_text(
        yaml.safe_dump(
            {"proxies": [{"name": "HK-A", "type": "ss", "server": "hk.example.com", "port": 443}]},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return paths


def make_runtime_config() -> ProxyLifecycleConfig:
    paths = make_lifecycle_paths()
    return ProxyLifecycleConfig(
        mihomo_path=str(paths["mihomo"]),
        config_path=str(paths["config"]),
        work_dir=str(paths["root"]),
        sub_path=str(paths["sub"]),
        custom_nodes_path=str(paths["custom"]),
    )


def make_base_config() -> dict[str, object]:
    return {
        "external-controller": "127.0.0.1:9090",
        "proxies": [{"name": "HK-A", "type": "ss", "server": "hk.example.com", "port": 443}],
        "proxy-groups": [{"name": "GLOBAL", "type": "select", "proxies": ["HK-A"]}],
    }


def make_exit_node(name: str = "relay") -> dict[str, object]:
    return {
        "name": f"{EXIT_PREFIX}{name}",
        "type": "http",
        "server": "na-relay.oneproxy.vip",
        "port": 1337,
        "username": "demo",
        "password": "secret",
    }


class FakeRegistryKey:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def __enter__(self) -> FakeRegistryKey:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    KEY_QUERY_VALUE = 2
    REG_DWORD = 4
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def OpenKey(  # noqa: N802
        self,
        root: str,
        path: str,
        reserved: int = 0,
        access: int = 0,
    ) -> FakeRegistryKey:
        _ = (root, path, reserved, access)
        return FakeRegistryKey(self.values)

    def SetValueEx(  # noqa: N802
        self,
        key: FakeRegistryKey,
        name: str,
        reserved: int,
        value_type: int,
        value: object,
    ) -> None:
        _ = (reserved, value_type)
        key.values[name] = value

    def QueryValueEx(  # noqa: N802
        self,
        key: FakeRegistryKey,
        name: str,
    ) -> tuple[object, int]:
        return key.values.get(name, 0), self.REG_DWORD


class FakeWininet:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def InternetSetOptionW(  # noqa: N802
        self,
        handle: int,
        option: int,
        buffer: int,
        length: int,
    ) -> int:
        _ = (handle, buffer, length)
        self.calls.append(option)
        return 1
