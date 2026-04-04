from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProxyConfig(BaseModel):
    """mihomo 启动配置。"""

    mihomo_path: str
    config_path: str
    work_dir: str
    api_url: str = "http://127.0.0.1:9090"
    api_secret: str = ""


class ProxyDelayRecord(BaseModel):
    """延迟历史记录。"""

    time: str
    delay: int


class ProxyNode(BaseModel):
    """单个代理节点信息。"""

    name: str
    type: str
    alive: bool = False
    delay: int = 0
    history: list[ProxyDelayRecord] = Field(default_factory=list)


class ProxyGroup(BaseModel):
    """代理组信息。"""

    name: str
    type: str
    now: str
    all: list[str] = Field(default_factory=list)


class ProxyStatus(BaseModel):
    """完整代理状态。"""

    version: str = ""
    groups: list[ProxyGroup] = Field(default_factory=list)
    nodes: list[ProxyNode] = Field(default_factory=list)


class DelayTestResult(BaseModel):
    """批量测速结果。"""

    results: dict[str, int] = Field(default_factory=dict)
    timeout_nodes: list[str] = Field(default_factory=list)
    fastest_node: str = ""
    fastest_delay: int = 0
    test_url: str = ""
    timestamp: str = ""


class ChainConfigState(BaseModel):
    exit_node: str = ""
    transit_pattern: str = ""
    transit_nodes: list[str] = Field(default_factory=list)


class CustomNodesState(BaseModel):
    exit_nodes: list[dict[str, Any]] = Field(default_factory=list)
    chain_config: ChainConfigState = Field(default_factory=ChainConfigState)


class ProxyLifecycleConfig(BaseModel):
    mihomo_path: str
    config_path: str
    work_dir: str
    sub_path: str
    custom_nodes_path: str
    api_url: str = "http://127.0.0.1:9090"
    api_secret: str = ""
    proxy_port: int = 7890


__all__ = [
    "ChainConfigState",
    "CustomNodesState",
    "DelayTestResult",
    "ProxyConfig",
    "ProxyDelayRecord",
    "ProxyGroup",
    "ProxyLifecycleConfig",
    "ProxyNode",
    "ProxyStatus",
]
