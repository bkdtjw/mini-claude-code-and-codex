from __future__ import annotations

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


__all__ = [
    "DelayTestResult",
    "ProxyConfig",
    "ProxyDelayRecord",
    "ProxyGroup",
    "ProxyNode",
    "ProxyStatus",
]
