from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .proxy_models import ProxyDelayRecord

GROUP_TYPES = {"selector", "urltest", "fallback", "loadbalance"}
SKIP_TYPES = {"direct", "reject", "compatible"}


class ProxyAPIError(Exception):
    """mihomo API 错误。"""


class APIRequest(BaseModel):
    """HTTP 请求参数。"""

    method: str
    path: str
    params: dict[str, str | int] = Field(default_factory=dict)
    json_body: dict[str, Any] = Field(default_factory=dict)
    timeout: float | None = None


def find_fastest(results: dict[str, int]) -> tuple[str, int]:
    available = [(name, delay) for name, delay in results.items() if delay > 0]
    return min(available, key=lambda item: item[1]) if available else ("", 0)


def parse_delay(payload: dict[str, Any]) -> int:
    return int(payload.get("delay") or 0) if isinstance(payload, dict) else 0


def parse_group_nodes(raw_nodes: object) -> list[str]:
    if not isinstance(raw_nodes, list):
        return []
    return [str(name) for name in raw_nodes if str(name).strip()]


def parse_history(raw_history: object) -> list[ProxyDelayRecord]:
    if not isinstance(raw_history, list):
        return []
    records: list[ProxyDelayRecord] = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        records.append(
            ProxyDelayRecord(
                time=str(item.get("time") or ""),
                delay=int(item.get("delay") or 0),
            )
        )
    return records


def normalize_type(proxy_type: str) -> str:
    return proxy_type.strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


__all__ = [
    "APIRequest",
    "GROUP_TYPES",
    "SKIP_TYPES",
    "ProxyAPIError",
    "find_fastest",
    "normalize_type",
    "now_text",
    "parse_delay",
    "parse_group_nodes",
    "parse_history",
]
