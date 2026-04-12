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
    uuid: str = ""
    network: str = ""
    flow: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""
    fingerprint: str = ""
    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str: return _validate_action(value, "add_exit")
    @field_validator("name", "type", "server")
    @classmethod
    def validate_required_text(cls, value: str) -> str: return _validate_text(value)
    @field_validator("password", "sni", "uuid", "network", "flow", "reality_public_key", "reality_short_id", "fingerprint")
    @classmethod
    def normalize_optional_text(cls, value: str) -> str: return value.strip()


class RemoveExitArgs(BaseModel):
    action: str
    name: str
    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str: return _validate_action(value, "remove_exit")
    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str: return _validate_text(value)


class SetChainArgs(BaseModel):
    action: str
    exit_node: str
    transit_nodes: list[str] = Field(default_factory=list)
    transit_pattern: str = ""
    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str: return _validate_action(value, "set")
    @field_validator("exit_node")
    @classmethod
    def validate_exit_node(cls, value: str) -> str: return _validate_text(value)
    @field_validator("transit_pattern")
    @classmethod
    def normalize_pattern(cls, value: str) -> str: return value.strip()
    @field_validator("transit_nodes")
    @classmethod
    def validate_nodes(cls, value: list[str]) -> list[str]: return [item.strip() for item in value if item.strip()]


class RemoveChainArgs(BaseModel):
    action: str
    exit_node: str = ""
    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str: return _validate_action(value, "remove")
    @field_validator("exit_node")
    @classmethod
    def normalize_exit_node(cls, value: str) -> str: return value.strip()


class ListChainArgs(BaseModel):
    action: str
    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str: return _validate_action(value, "list")


ChainArgs = AddExitArgs | RemoveExitArgs | SetChainArgs | RemoveChainArgs | ListChainArgs


def parse_chain_args(args: dict[str, object]) -> ChainArgs:
    action = str(args.get("action") or "").strip()
    model = {"add_exit": AddExitArgs, "remove_exit": RemoveExitArgs, "set": SetChainArgs, "remove": RemoveChainArgs, "list": ListChainArgs}.get(action)
    if model is None:
        raise ChainProxyError("action must be one of: add_exit, remove_exit, set, remove, list")
    try:
        parsed = model.model_validate(args)
    except ValidationError as exc:
        raise ChainProxyError(exc.errors()[0].get("msg", "Invalid proxy_chain arguments")) from exc
    if isinstance(parsed, SetChainArgs) and parsed.transit_nodes and parsed.transit_pattern:
        raise ChainProxyError("transit_nodes and transit_pattern are mutually exclusive")
    return parsed


def build_add_exit_extra(args: AddExitArgs) -> dict[str, Any]:
    extra = dict(args.extra)
    for key, value in {"uuid": args.uuid, "network": args.network, "flow": args.flow, "client-fingerprint": args.fingerprint}.items():
        if value:
            extra[key] = value
    if args.type.lower() == "vless":
        extra.setdefault("udp", True)
        if args.sni and "servername" not in extra:
            extra["servername"] = args.sni
    if args.reality_public_key:
        reality_opts = dict(extra.get("reality-opts") or {})
        reality_opts["public-key"] = args.reality_public_key
        if args.reality_short_id:
            reality_opts["short-id"] = args.reality_short_id
        extra["reality-opts"] = reality_opts
        extra["tls"] = True
    return extra


def format_add_exit_output(node: dict[str, Any]) -> str:
    return "\n".join([f"Exit node added: {node['name']}", f"Protocol: {node['type']}", f"Server: {node['server']}:{node['port']}", "Synced to GLOBAL group"])


def format_remove_exit_output(name: str) -> str:
    return f"Exit node removed: {name}"


def format_set_output(exit_node: str, created: int, mode: str, chains: list[dict[str, str]]) -> str:
    lines = ["Chain proxy configured", f"Exit node: {exit_node}", f"Match mode: {mode}", f"Chain nodes created: {created}"]
    if chains:
        lines.append(f"Example chain: {chains[0]['name']}")
    return "\n".join(lines)


def format_remove_output(removed: int, exit_node: str | None) -> str:
    return f"{f'Chain proxy removed: {exit_node}' if exit_node else 'Chain proxy removed'}\nRemoved chain nodes: {removed}"


def format_list_output(exit_nodes: list[dict[str, Any]], chains: list[dict[str, str]]) -> str:
    exit_lines = ["Exit nodes:"] + ([f"  {node['name']} ({node['type']}, {node['server']}:{node['port']})" for node in exit_nodes] or ["  None"])
    chain_lines = [f"Chain nodes ({len(chains)}):"] + ([f"  {item['name']}" for item in chains] or ["  None"])
    return "\n\n".join(["\n".join(exit_lines), "\n".join(chain_lines)])


def _validate_action(value: str, expected: str) -> str:
    text = _validate_text(value)
    if text != expected:
        raise ValueError(f"action must be {expected}")
    return text


def _validate_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Value cannot be empty")
    return text


__all__ = ["AddExitArgs", "ChainArgs", "ListChainArgs", "RemoveChainArgs", "RemoveExitArgs", "SetChainArgs", "build_add_exit_extra", "format_add_exit_output", "format_list_output", "format_remove_exit_output", "format_remove_output", "format_set_output", "parse_chain_args"]
