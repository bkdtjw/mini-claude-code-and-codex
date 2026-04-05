from __future__ import annotations

from typing import Any

EXIT_PREFIX = "EXIT-"
CHAIN_PREFIX = "CHAIN-"
CHAIN_GROUP_NAME = "Chain"
CHAIN_SEPARATOR = "__TO__"
SKIP_PROXY_TYPES = {"direct", "reject"}


class ChainProxyError(Exception):
    """Chain proxy config error."""


def ensure_list(config: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = config.get(key)
    if isinstance(value, list):
        return value
    config[key] = []
    return config[key]


def find_proxy(proxies: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((proxy for proxy in proxies if str(proxy.get("name") or "") == name), None)


def find_group(groups: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((group for group in groups if str(group.get("name") or "") == name), None)


def append_name_to_groups(
    groups: list[dict[str, Any]],
    name: str,
    skipped_groups: set[str] | None = None,
) -> None:
    for group in groups:
        group_name = str(group.get("name") or "")
        if skipped_groups and group_name in skipped_groups:
            continue
        options = group.get("proxies")
        if isinstance(options, list) and name not in options:
            options.append(name)


def append_global_group(groups: list[dict[str, Any]], name: str) -> None:
    global_group = find_group(groups, "GLOBAL")
    if global_group is None:
        global_group = {"name": "GLOBAL", "type": "select", "proxies": []}
        groups.append(global_group)
    options = global_group.setdefault("proxies", [])
    if isinstance(options, list) and name not in options:
        options.append(name)


def remove_group_refs(groups: list[dict[str, Any]], names: set[str]) -> None:
    for group in groups:
        options = group.get("proxies")
        if isinstance(options, list):
            group["proxies"] = [item for item in options if item not in names]


def upsert_chain_group(groups: list[dict[str, Any]], chain_names_list: list[str]) -> None:
    chain_group = find_group(groups, CHAIN_GROUP_NAME)
    if chain_group is None:
        groups.append({"name": CHAIN_GROUP_NAME, "type": "select", "proxies": chain_names_list})
        return
    chain_group["type"] = "select"
    chain_group["proxies"] = chain_names_list


def chain_names(proxies: list[dict[str, Any]]) -> list[str]:
    return [str(proxy.get("name") or "") for proxy in proxies if is_chain_proxy(proxy)]


def build_chain_name(transit: str, exit_name: str) -> str:
    return f"{CHAIN_PREFIX}{transit}{CHAIN_SEPARATOR}{exit_name}"


def is_chain_proxy(proxy: dict[str, Any]) -> bool:
    return str(proxy.get("name") or "").startswith(CHAIN_PREFIX)


def chain_exit(proxy: dict[str, Any]) -> str:
    name = str(proxy.get("name") or "")
    transit = str(proxy.get("dialer-proxy") or "")
    prefix = f"{CHAIN_PREFIX}{transit}{CHAIN_SEPARATOR}"
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name.split(CHAIN_SEPARATOR, maxsplit=1)[-1].strip()


def is_transit_candidate(proxy: dict[str, Any] | None, exit_name: str) -> bool:
    if proxy is None:
        return False
    name = str(proxy.get("name") or "")
    proxy_type = str(proxy.get("type") or "").lower()
    return (
        bool(name)
        and name != exit_name
        and not name.startswith(EXIT_PREFIX)
        and not name.startswith(CHAIN_PREFIX)
        and proxy_type not in SKIP_PROXY_TYPES
    )


def normalize_exit_name(name: str | None) -> str:
    text = unique_text(name)
    if not text:
        raise ChainProxyError("Node name cannot be empty")
    return text if text.startswith(EXIT_PREFIX) else f"{EXIT_PREFIX}{text}"


def unique_text(value: str | None) -> str:
    return (value or "").strip()


__all__ = [
    "CHAIN_GROUP_NAME",
    "CHAIN_PREFIX",
    "CHAIN_SEPARATOR",
    "EXIT_PREFIX",
    "SKIP_PROXY_TYPES",
    "ChainProxyError",
    "append_global_group",
    "append_name_to_groups",
    "build_chain_name",
    "chain_exit",
    "chain_names",
    "ensure_list",
    "find_group",
    "find_proxy",
    "is_chain_proxy",
    "is_transit_candidate",
    "normalize_exit_name",
    "remove_group_refs",
    "unique_text",
    "upsert_chain_group",
]
