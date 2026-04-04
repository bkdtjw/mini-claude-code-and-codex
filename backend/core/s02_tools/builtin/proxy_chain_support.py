from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from .proxy_chain_utils import ChainProxyError


class AddExitArgs(BaseModel):
    action: str
    name: str
    type: str = "trojan"
    server: str
    port: int = Field(ge=1, le=65535)
    password: str = ""
    sni: str = ""
    skip_cert_verify: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        return _validate_action(value, "add_exit")

    @field_validator("name", "type", "server")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _validate_text(value)

    @field_validator("password", "sni")
    @classmethod
    def normalize_optional_text(cls, value: str) -> str:
        return value.strip()


class RemoveExitArgs(BaseModel):
    action: str
    name: str

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        return _validate_action(value, "remove_exit")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_text(value)


class SetChainArgs(BaseModel):
    action: str
    exit_node: str
    transit_nodes: list[str] = Field(default_factory=list)
    transit_pattern: str = ""

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        return _validate_action(value, "set")

    @field_validator("exit_node")
    @classmethod
    def validate_exit_node(cls, value: str) -> str:
        return _validate_text(value)

    @field_validator("transit_pattern")
    @classmethod
    def normalize_pattern(cls, value: str) -> str:
        return value.strip()

    @field_validator("transit_nodes")
    @classmethod
    def validate_nodes(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class RemoveChainArgs(BaseModel):
    action: str
    exit_node: str = ""

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        return _validate_action(value, "remove")

    @field_validator("exit_node")
    @classmethod
    def normalize_exit_node(cls, value: str) -> str:
        return value.strip()


class ListChainArgs(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        return _validate_action(value, "list")


ChainArgs = AddExitArgs | RemoveExitArgs | SetChainArgs | RemoveChainArgs | ListChainArgs


def parse_chain_args(args: dict[str, object]) -> ChainArgs:
    action = str(args.get("action") or "").strip()
    model_map: dict[str, type[BaseModel]] = {
        "add_exit": AddExitArgs,
        "remove_exit": RemoveExitArgs,
        "set": SetChainArgs,
        "remove": RemoveChainArgs,
        "list": ListChainArgs,
    }
    model = model_map.get(action)
    if model is None:
        raise ChainProxyError("action 必须是 add_exit、remove_exit、set、remove 或 list")
    try:
        parsed = model.model_validate(args)
    except ValidationError as exc:
        raise ChainProxyError(exc.errors()[0].get("msg", "proxy_chain 参数错误")) from exc
    if isinstance(parsed, SetChainArgs) and parsed.transit_nodes and parsed.transit_pattern:
        raise ChainProxyError("transit_nodes 和 transit_pattern 只能二选一")
    return parsed


def format_add_exit_output(node: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"已添加落地节点: {node['name']}",
            f"协议类型: {node['type']}",
            f"服务器: {node['server']}:{node['port']}",
            "已同步到 GLOBAL 代理组",
        ]
    )


def format_remove_exit_output(name: str) -> str:
    return f"已移除落地节点: {name}"


def format_set_output(exit_node: str, created: int, mode: str, chains: list[dict[str, str]]) -> str:
    lines = [
        "链式代理配置完成",
        f"落地节点: {exit_node}",
        f"匹配模式: {mode}",
        f"创建链式节点: {created} 个",
    ]
    if chains:
        lines.append(f"示例链路: {chains[0]['name']}")
    return "\n".join(lines)


def format_remove_output(removed: int, exit_node: str | None) -> str:
    target = f"已移除落地节点 {exit_node} 的链式配置" if exit_node else "已移除全部链式配置"
    return f"{target}\n删除链式节点: {removed} 个"


def format_list_output(exit_nodes: list[dict[str, Any]], chains: list[dict[str, str]]) -> str:
    exit_lines = ["落地节点:"] + (
        [
            f"  {node['name']} ({node['type']}, {node['server']}:{node['port']})"
            for node in exit_nodes
        ]
        or ["  无"]
    )
    chain_lines = [f"链式节点 ({len(chains)}):"] + (
        [f"  {item['name']}" for item in chains] or ["  无"]
    )
    return "\n\n".join(["\n".join(exit_lines), "\n".join(chain_lines)])


def _validate_action(value: str, expected: str) -> str:
    text = _validate_text(value)
    if text != expected:
        raise ValueError(f"action 必须是 {expected}")
    return text


def _validate_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("参数不能为空")
    return text


__all__ = [
    "AddExitArgs",
    "ChainArgs",
    "ListChainArgs",
    "RemoveChainArgs",
    "RemoveExitArgs",
    "SetChainArgs",
    "format_add_exit_output",
    "format_list_output",
    "format_remove_exit_output",
    "format_remove_output",
    "format_set_output",
    "parse_chain_args",
]
