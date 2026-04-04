from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator

from .proxy_models import DelayTestResult, ProxyGroup, ProxyNode, ProxyStatus

DEFAULT_TEST_URL = "http://www.gstatic.com/generate_204"
OFFLINE_MESSAGE = "mihomo API 不可用，请确认 mihomo 已启动且 RESTful API 已开启"
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
            raise ValueError("参数不能为空")
        return text


class ProxySwitchArgs(BaseModel):
    node: str
    group: str = "GLOBAL"

    @field_validator("node", "group")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("参数不能为空")
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
            raise ValueError("action 必须是 inject、remove 或 import")
        return value

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        if value and value not in {"h2mux", "yamux", "smux"}:
            raise ValueError("protocol 必须是 h2mux、yamux 或 smux")
        return value or "h2mux"


def parse_status_args(args: dict[str, object]) -> ProxyStatusArgs:
    return _parse_args(ProxyStatusArgs, args, "proxy_status 参数错误")


def parse_test_args(args: dict[str, object]) -> ProxyTestArgs:
    return _parse_args(ProxyTestArgs, args, "proxy_test 参数错误")


def parse_switch_args(args: dict[str, object]) -> ProxySwitchArgs:
    return _parse_args(ProxySwitchArgs, args, "proxy_switch 参数错误")


def parse_optimize_args(args: dict[str, object]) -> ProxyOptimizeArgs:
    params = _parse_args(ProxyOptimizeArgs, args, "proxy_optimize 参数错误")
    if params.action == "import" and not params.subscription_url:
        raise ProxyToolError("导入订阅时必须提供 subscription_url")
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
    lines = [f"mihomo {version or '未知版本'}", ""]
    for group in groups:
        lines.extend(
            [
                f"代理组: {group.name}",
                f"  当前节点: {group.now or '未选择'}",
                f"  可用节点: {_format_group_nodes(group, node_map)}",
                "",
            ]
        )
    alive = sum(1 for node in status.nodes if node.alive)
    total = len(status.nodes)
    lines.append(f"节点总数: {total} | 存活: {alive} | 超时: {total - alive}")
    return "\n".join(lines).strip()


def format_test_output(result: DelayTestResult, group_name: str) -> str:
    ranked = sorted(
        ((name, delay) for name, delay in result.results.items() if delay > 0),
        key=lambda item: item[1],
    )
    timeouts = [name for name, delay in result.results.items() if delay <= 0]
    lines = [
        f"测速完成 ({result.timestamp})",
        f"测速 URL: {result.test_url}",
        f"代理组: {group_name}",
        "",
        "排名  节点                  延迟",
    ]
    for index, (name, delay) in enumerate(ranked, start=1):
        lines.append(f"{index:<4}  {name:<20}  {delay}ms")
    for name in timeouts:
        lines.append(f"---   {name:<20}  超时")
    fastest = (
        f"{result.fastest_node} ({result.fastest_delay}ms)"
        if result.fastest_node
        else "无可用节点"
    )
    lines.extend(
        [
            "",
            f"最快节点: {fastest}",
            (
                f"存活: {len(ranked)}/{len(result.results)} | "
                f"超时: {len(timeouts)}/{len(result.results)}"
            ),
        ]
    )
    return "\n".join(lines)


def format_delay(delay: int) -> str:
    return f"{delay}ms" if delay > 0 else "超时"


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
        raise ProxyToolError(f"未找到代理组: {group_filter}")
    return filtered


def _format_group_nodes(group: ProxyGroup, node_map: dict[str, ProxyNode]) -> str:
    if not group.all:
        return "无"
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
