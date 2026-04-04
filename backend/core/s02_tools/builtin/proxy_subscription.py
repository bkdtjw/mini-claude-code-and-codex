from __future__ import annotations

import base64
import json
from typing import Any

import httpx

REQUEST_TIMEOUT_SECONDS = 30.0
PLAIN_PREFIXES = ("port:", "mixed-port:", "proxies:", "{")


class SubscriptionError(Exception):
    """订阅拉取或解析失败。"""


async def fetch_subscription(url: str, user_agent: str = "clash.meta") -> str:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False) as client:
            response = await client.get(url, headers={"User-Agent": user_agent})
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as exc:
        raise SubscriptionError(f"拉取订阅失败: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise SubscriptionError(f"拉取订阅失败: {exc}") from exc


def decode_subscription(raw: str) -> str:
    stripped = raw.strip()
    if not stripped:
        raise SubscriptionError("订阅内容为空")
    if stripped.startswith(PLAIN_PREFIXES):
        return stripped
    try:
        compact = "".join(stripped.split())
        decoded = base64.b64decode(compact + ("=" * ((-len(compact)) % 4))).decode("utf-8")
        return decoded.strip()
    except Exception as exc:  # noqa: BLE001
        raise SubscriptionError(f"订阅内容解码失败: {exc}") from exc


def parse_subscription_yaml(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise SubscriptionError("订阅内容为空")
    try:
        payload = _load_with_yaml(stripped) or _load_with_fallback(stripped)
    except Exception as exc:  # noqa: BLE001
        raise SubscriptionError(f"解析订阅失败: {exc}") from exc
    if isinstance(payload, list):
        payload = {"proxies": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("proxies"), list):
        raise SubscriptionError("订阅配置缺少 proxies 列表")
    return payload


async def load_subscription(url: str) -> dict[str, Any]:
    try:
        raw = await fetch_subscription(url)
        return parse_subscription_yaml(decode_subscription(raw))
    except SubscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SubscriptionError(f"加载订阅失败: {exc}") from exc


def _load_with_yaml(text: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    payload = yaml.safe_load(text)
    return payload if isinstance(payload, (dict, list)) else None


def _load_with_fallback(text: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    if text.startswith("{"):
        payload = json.loads(text)
        return payload if isinstance(payload, (dict, list)) else None
    proxies = _extract_simple_proxies(text)
    return {"proxies": proxies} if proxies else None


def _extract_simple_proxies(text: str) -> list[dict[str, Any]]:
    proxies: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_proxies = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "proxies:":
            in_proxies = True
            continue
        if not in_proxies:
            continue
        if stripped.startswith("- "):
            if current:
                proxies.append(current)
            current = _parse_mapping_line(stripped[2:])
            continue
        if current is not None and ":" in stripped and line.startswith("  "):
            current.update(_parse_mapping_line(stripped))
    if current:
        proxies.append(current)
    return proxies


def _parse_mapping_line(line: str) -> dict[str, Any]:
    key, value = line.split(":", maxsplit=1)
    return {key.strip(): _parse_scalar(value.strip())}


def _parse_scalar(value: str) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if value.isdigit():
        return int(value)
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        return value[1:-1]
    return value


__all__ = [
    "SubscriptionError",
    "decode_subscription",
    "fetch_subscription",
    "load_subscription",
    "parse_subscription_yaml",
]
