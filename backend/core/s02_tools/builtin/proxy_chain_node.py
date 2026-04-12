from __future__ import annotations

import copy
from typing import Any


def build_exit_node(
    name: str,
    node_type: str,
    server: str,
    port: int,
    password: str,
    sni: str,
    skip_cert_verify: bool,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    extra_data = copy.deepcopy(extra or {})
    _drop_empty_fields(extra_data)
    node = {
        "name": name,
        "type": node_type.strip().lower(),
        "server": server,
        "port": port,
    }
    if node["type"] == "vless":
        _apply_vless_fields(node, sni, extra_data)
    else:
        if password:
            node["password"] = password
        if sni:
            node["sni"] = sni
    if skip_cert_verify:
        node["skip-cert-verify"] = True
    if extra_data:
        node.update(extra_data)
    node.pop("dialer-proxy", None)
    return node


def _apply_vless_fields(node: dict[str, Any], sni: str, extra_data: dict[str, Any]) -> None:
    extra_data.pop("password", None)
    servername = str(
        extra_data.pop("servername", "") or extra_data.pop("sni", "") or sni
    ).strip()
    if servername:
        node["servername"] = servername


def _drop_empty_fields(extra_data: dict[str, Any]) -> None:
    for key in ("password", "sni", "servername"):
        if not extra_data.get(key):
            extra_data.pop(key, None)
    if not extra_data.get("skip-cert-verify"):
        extra_data.pop("skip-cert-verify", None)
