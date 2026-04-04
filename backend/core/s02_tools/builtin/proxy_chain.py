from __future__ import annotations

import copy
from typing import Any

from .proxy_chain_utils import (
    CHAIN_GROUP_NAME,
    CHAIN_PREFIX,
    EXIT_PREFIX,
    ChainProxyError,
    append_global_group,
    append_name_to_groups,
    build_chain_name,
    chain_exit,
    chain_names,
    ensure_list,
    find_group,
    find_proxy,
    is_chain_proxy,
    is_transit_candidate,
    normalize_exit_name,
    remove_group_refs,
    unique_text,
    upsert_chain_group,
)


class ChainProxyManager:
    """链式代理配置管理器。"""

    @staticmethod
    def add_exit_node(
        config: dict[str, Any],
        name: str,
        node_type: str,
        server: str,
        port: int,
        password: str,
        sni: str = "",
        skip_cert_verify: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = copy.deepcopy(config)
        exit_name = normalize_exit_name(name)
        node = _build_exit_node(
            exit_name, node_type, server, port, password, sni, skip_cert_verify, extra
        )
        proxies = ensure_list(result, "proxies")
        current = find_proxy(proxies, exit_name)
        if current is None:
            proxies.append(node)
        else:
            current.clear()
            current.update(node)
        append_name_to_groups(ensure_list(result, "proxy-groups"), exit_name, {CHAIN_GROUP_NAME})
        return result

    @staticmethod
    def remove_exit_node(config: dict[str, Any], name: str) -> dict[str, Any]:
        exit_name = normalize_exit_name(name)
        result, _ = ChainProxyManager.remove_chain(config, exit_name)
        proxies = ensure_list(result, "proxies")
        proxies[:] = [proxy for proxy in proxies if str(proxy.get("name") or "") != exit_name]
        remove_group_refs(ensure_list(result, "proxy-groups"), {exit_name})
        for proxy in proxies:
            if proxy.get("dialer-proxy") == exit_name:
                proxy.pop("dialer-proxy", None)
        return result

    @staticmethod
    def set_chain(
        config: dict[str, Any],
        exit_node: str,
        transit_nodes: list[str] | None = None,
        transit_pattern: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        if transit_nodes and transit_pattern:
            raise ChainProxyError("transit_nodes 和 transit_pattern 只能二选一")
        exit_name = normalize_exit_name(exit_node)
        result, _ = ChainProxyManager.remove_chain(config, exit_name)
        proxies = ensure_list(result, "proxies")
        exit_proxy = find_proxy(proxies, exit_name)
        if exit_proxy is None:
            raise ChainProxyError(f"未找到落地节点: {exit_name}")
        exit_proxy.pop("dialer-proxy", None)
        transits = _select_transits(proxies, exit_name, transit_nodes, transit_pattern)
        if not transits:
            raise ChainProxyError("未找到可用的中转节点")
        for transit in transits:
            virtual = copy.deepcopy(exit_proxy)
            virtual["name"] = build_chain_name(transit, exit_name)
            virtual["dialer-proxy"] = transit
            proxies.append(virtual)
        groups = ensure_list(result, "proxy-groups")
        upsert_chain_group(groups, chain_names(proxies))
        append_global_group(groups, CHAIN_GROUP_NAME)
        return result, len(transits)

    @staticmethod
    def remove_chain(
        config: dict[str, Any],
        exit_node: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        result = copy.deepcopy(config)
        proxies = ensure_list(result, "proxies")
        target_exit = normalize_exit_name(exit_node) if exit_node else None
        removed = {
            str(proxy.get("name") or "")
            for proxy in proxies
            if is_chain_proxy(proxy) and (target_exit is None or chain_exit(proxy) == target_exit)
        }
        if not removed:
            return result, 0
        proxies[:] = [proxy for proxy in proxies if str(proxy.get("name") or "") not in removed]
        groups = ensure_list(result, "proxy-groups")
        remove_group_refs(groups, removed)
        remaining = chain_names(proxies)
        chain_group = find_group(groups, CHAIN_GROUP_NAME)
        if chain_group is not None and remaining:
            chain_group["proxies"] = remaining
        elif chain_group is not None:
            groups[:] = [
                group
                for group in groups
                if str(group.get("name") or "") != CHAIN_GROUP_NAME
            ]
            remove_group_refs(groups, {CHAIN_GROUP_NAME})
        return result, len(removed)

    @staticmethod
    def list_chains(config: dict[str, Any]) -> list[dict[str, str]]:
        chains: list[dict[str, str]] = []
        for proxy in ensure_list(copy.deepcopy(config), "proxies"):
            if not is_chain_proxy(proxy):
                continue
            name = str(proxy.get("name") or "")
            transit = str(proxy.get("dialer-proxy") or "")
            chains.append({"name": name, "transit": transit, "exit": chain_exit(proxy)})
        return chains

    @staticmethod
    def list_exit_nodes(config: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "name": str(proxy.get("name") or ""),
                "type": str(proxy.get("type") or ""),
                "server": str(proxy.get("server") or ""),
                "port": int(proxy.get("port") or 0),
            }
            for proxy in ensure_list(copy.deepcopy(config), "proxies")
            if str(proxy.get("name") or "").startswith(EXIT_PREFIX)
        ]


def _build_exit_node(
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
    if not extra_data.get("password"):
        extra_data.pop("password", None)
    if not extra_data.get("sni"):
        extra_data.pop("sni", None)
    if not extra_data.get("skip-cert-verify"):
        extra_data.pop("skip-cert-verify", None)
    node = {
        "name": name,
        "type": node_type,
        "server": server,
        "port": port,
    }
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


def _select_transits(
    proxies: list[dict[str, Any]],
    exit_name: str,
    transit_nodes: list[str] | None,
    transit_pattern: str | None,
) -> list[str]:
    if transit_nodes:
        names = [unique_text(name) for name in transit_nodes if unique_text(name)]
        invalid = [
            name
            for name in names
            if not is_transit_candidate(find_proxy(proxies, name), exit_name)
        ]
        if invalid:
            raise ChainProxyError(f"以下中转节点不可用: {', '.join(invalid)}")
        return list(dict.fromkeys(names))
    lowered = (transit_pattern or "").strip().lower()
    return [
        str(proxy.get("name") or "")
        for proxy in proxies
        if is_transit_candidate(proxy, exit_name)
        and (not lowered or lowered in str(proxy.get("name") or "").lower())
    ]


__all__ = [
    "CHAIN_GROUP_NAME",
    "CHAIN_PREFIX",
    "ChainProxyError",
    "ChainProxyManager",
    "EXIT_PREFIX",
]
