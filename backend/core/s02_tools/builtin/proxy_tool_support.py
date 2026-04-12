from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator

from .proxy_models import DelayTestResult, ProxyGroup, ProxyNode, ProxyStatus

DEFAULT_TEST_URL = "http://www.gstatic.com/generate_204"
OFFLINE_MESSAGE = "mihomo API unavailable"
T = TypeVar("T", bound=BaseModel)


class ProxyToolError(Exception):
    """Proxy tool error."""


class ProxyStatusArgs(BaseModel):
    group: str = ""

    @field_validator("group")
    @classmethod
    def normalize_group(cls, value: str) -> str:
        return value.strip()


class ProxyTestArgs(BaseModel):
    group: str = "GLOBAL"
    timeout: int = Field(default=5000, ge=1, le=60000)
    url: str = DEFAULT_TEST_URL

    @field_validator("group", "url")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Value cannot be empty")
        return text


class ProxySwitchArgs(BaseModel):
    node: str
    group: str = "GLOBAL"

    @field_validator("node", "group")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Value cannot be empty")
        return text


class ProxyOptimizeArgs(BaseModel):
    action: str
    subscription_url: str = ""
    up: int = Field(default=50, ge=1, le=10000)
    down: int = Field(default=100, ge=1, le=10000)
    protocol: str = "h2mux"
    smux: bool = False

    @field_validator("action", "subscription_url", "protocol")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in {"inject", "remove", "import"}:
            raise ValueError("action must be one of: inject, remove, import")
        return value

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        if value and value not in {"h2mux", "yamux", "smux"}:
            raise ValueError("protocol must be one of: h2mux, yamux, smux")
        return value or "h2mux"


def parse_status_args(args: dict[str, object]) -> ProxyStatusArgs:
    return _parse_args(ProxyStatusArgs, args, "Invalid proxy_status arguments")


def parse_test_args(args: dict[str, object]) -> ProxyTestArgs:
    return _parse_args(ProxyTestArgs, args, "Invalid proxy_test arguments")


def parse_switch_args(args: dict[str, object]) -> ProxySwitchArgs:
    return _parse_args(ProxySwitchArgs, args, "Invalid proxy_switch arguments")


def parse_optimize_args(args: dict[str, object]) -> ProxyOptimizeArgs:
    params = _parse_args(ProxyOptimizeArgs, args, "Invalid proxy_optimize arguments")
    if params.action == "import" and not params.subscription_url:
        raise ProxyToolError("subscription_url is required for import")
    return params


def fuzzy_match(keyword: str, candidates: list[str]) -> list[str]:
    exact = [name for name in candidates if name == keyword]
    if exact:
        return exact
    lowered = keyword.lower()
    contains = [name for name in candidates if lowered in name.lower()]
    if contains:
        return contains
    tokens = [token for token in re.split(r"[\s/_-]+", lowered) if token]
    return [name for name in candidates if all(token in name.lower() for token in tokens)]


def format_status_output(status: ProxyStatus, version: str, group_filter: str) -> str:
    groups = _select_groups(status.groups, group_filter)
    node_map = {node.name: node for node in status.nodes}
    lines = [f"mihomo {version or 'unknown'}", ""]
    for group in groups:
        lines.extend([f"Group: {group.name}", f"  Current node: {group.now or 'None'}", f"  Available nodes: {_format_group_nodes(group, node_map)}", ""])
    alive = sum(1 for node in status.nodes if node.alive)
    total = len(status.nodes)
    lines.append(f"Total nodes: {total} | Alive: {alive} | Timeout: {total - alive}")
    return "\n".join(lines).strip()


def format_test_output(result: DelayTestResult, group_name: str) -> str:
    ranked = sorted(((name, delay) for name, delay in result.results.items() if delay > 0), key=lambda item: item[1])
    timeouts = [name for name, delay in result.results.items() if delay <= 0]
    lines = [f"Delay test complete ({result.timestamp})", f"Test URL: {result.test_url}", f"Group: {group_name}", "", "Rank  Node                  Delay"]
    lines.extend(f"{index:<4}  {name:<20}  {delay}ms" for index, (name, delay) in enumerate(ranked, start=1))
    lines.extend(f"---   {name:<20}  Timeout" for name in timeouts)
    fastest = f"{result.fastest_node} ({result.fastest_delay}ms)" if result.fastest_node else "None"
    lines.extend(["", f"Fastest node: {fastest}", f"Alive: {len(ranked)}/{len(result.results)} | Timeout: {len(timeouts)}/{len(result.results)}"])
    return "\n".join(lines)


def format_delay(delay: int) -> str:
    return f"{delay}ms" if delay > 0 else "Timeout"


def _parse_args(model: type[T], args: dict[str, object], message: str) -> T:  # noqa: UP047
    try:
        return model.model_validate(args)
    except ValidationError as exc:
        raise ProxyToolError(exc.errors()[0].get("msg", message)) from exc


def _select_groups(groups: list[ProxyGroup], group_filter: str) -> list[ProxyGroup]:
    if not group_filter:
        return groups
    filtered = [group for group in groups if group.name == group_filter]
    if not filtered:
        raise ProxyToolError(f"Proxy group {group_filter} not found")
    return filtered


def _format_group_nodes(group: ProxyGroup, node_map: dict[str, ProxyNode]) -> str:
    if not group.all:
        return "None"
    values = []
    for name in group.all:
        node = node_map.get(name)
        values.append(name if node is None else f"{name}({format_delay(node.delay)})")
    return ", ".join(values)


__all__ = [
    "DEFAULT_TEST_URL",
    "OFFLINE_MESSAGE",
    "ProxyOptimizeArgs",
    "ProxyStatusArgs",
    "ProxySwitchArgs",
    "ProxyTestArgs",
    "ProxyToolError",
    "format_delay",
    "format_status_output",
    "format_test_output",
    "fuzzy_match",
    "parse_optimize_args",
    "parse_status_args",
    "parse_switch_args",
    "parse_test_args",
]
