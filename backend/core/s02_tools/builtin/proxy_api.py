from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .proxy_api_support import (
    GROUP_TYPES,
    SKIP_TYPES,
    APIRequest,
    ProxyAPIError,
    find_fastest,
    normalize_type,
    now_text,
    parse_delay,
    parse_group_nodes,
    parse_history,
)
from .proxy_models import DelayTestResult, ProxyGroup, ProxyNode, ProxyStatus

REQUEST_TIMEOUT_SECONDS = 10.0


class MihomoAPI:
    """mihomo RESTful API client."""

    def __init__(self, base_url: str = "http://127.0.0.1:9090", secret: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret.strip()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._secret}"} if self._secret else {}

    async def get_version(self) -> str:
        try:
            payload = await self._request_json(APIRequest(method="GET", path="/version"))
            return str(payload.get("version") or "")
        except ProxyAPIError:
            return ""

    async def get_proxies(self) -> ProxyStatus:
        try:
            payload = await self._request_json(APIRequest(method="GET", path="/proxies"))
            proxies = payload.get("proxies")
            if not isinstance(proxies, dict):
                return ProxyStatus()
            groups: list[ProxyGroup] = []
            nodes: list[ProxyNode] = []
            for name, raw in proxies.items():
                if not isinstance(raw, dict):
                    continue
                proxy_type = str(raw.get("type") or "")
                normalized = normalize_type(proxy_type)
                if normalized in SKIP_TYPES:
                    continue
                if normalized in GROUP_TYPES:
                    groups.append(
                        ProxyGroup(
                            name=str(name),
                            type=proxy_type,
                            now=str(raw.get("now") or ""),
                            all=parse_group_nodes(raw.get("all")),
                        )
                    )
                    continue
                history = parse_history(raw.get("history"))
                nodes.append(
                    ProxyNode(
                        name=str(name),
                        type=proxy_type,
                        alive=bool(raw.get("alive")),
                        delay=history[-1].delay if history else 0,
                        history=history,
                    )
                )
            return ProxyStatus(groups=groups, nodes=nodes)
        except ProxyAPIError:
            return ProxyStatus()

    async def get_delay(
        self,
        node_name: str,
        timeout: int = 5000,
        test_url: str = "http://www.gstatic.com/generate_204",
    ) -> int:
        try:
            payload = await self._request_json(
                APIRequest(
                    method="GET",
                    path=f"/proxies/{quote(node_name, safe='')}/delay",
                    params={"timeout": timeout, "url": test_url},
                )
            )
            return parse_delay(payload)
        except ProxyAPIError:
            return 0

    async def test_group_delay(
        self,
        group_name: str,
        timeout: int = 5000,
        test_url: str = "http://www.gstatic.com/generate_204",
    ) -> DelayTestResult:
        try:
            http_timeout = timeout / 1000 + 15.0
            payload = await self._request_json(
                APIRequest(
                    method="GET",
                    path=f"/group/{quote(group_name, safe='')}/delay",
                    params={"timeout": timeout, "url": test_url},
                    timeout=http_timeout,
                )
            )
            results = {
                str(name): int(delay or 0)
                for name, delay in payload.items()
                if isinstance(name, str)
                and name != "message"
                and isinstance(delay, (int, float))
            }
            fastest_name, fastest_delay = find_fastest(results)
            return DelayTestResult(
                results=results,
                timeout_nodes=[name for name, delay in results.items() if delay <= 0],
                fastest_node=fastest_name,
                fastest_delay=fastest_delay,
                test_url=test_url,
                timestamp=now_text(),
            )
        except ProxyAPIError:
            return DelayTestResult(test_url=test_url, timestamp=now_text())

    async def switch_proxy(self, group_name: str, node_name: str) -> bool:
        try:
            await self._request(
                APIRequest(
                    method="PUT",
                    path=f"/proxies/{quote(group_name, safe='')}",
                    json_body={"name": node_name},
                )
            )
            return True
        except ProxyAPIError:
            return False

    async def reload_config(self, config_path: str) -> bool:
        try:
            await self._request(APIRequest(method="PUT", path="/configs", json_body={"path": config_path}))
            return True
        except ProxyAPIError:
            return False

    async def get_connections(self) -> dict[str, object]:
        try:
            payload = await self._request_json(APIRequest(method="GET", path="/connections"))
            return {str(key): value for key, value in payload.items()}
        except ProxyAPIError:
            return {}

    async def _request(self, request: APIRequest) -> httpx.Response:
        try:
            effective_timeout = request.timeout if request.timeout is not None else REQUEST_TIMEOUT_SECONDS
            async with httpx.AsyncClient(timeout=effective_timeout, trust_env=False) as client:
                response = await client.request(
                    request.method,
                    f"{self._base_url}{request.path}",
                    headers=self._headers(),
                    params=request.params or None,
                    json=request.json_body or None,
                )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise ProxyAPIError(f"Failed to request mihomo API: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ProxyAPIError(f"Failed to request mihomo API: {exc}") from exc

    async def _request_json(self, request: APIRequest) -> dict[str, Any]:
        try:
            response = await self._request(request)
            if not response.content:
                return {}
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except ProxyAPIError:
            raise
        except ValueError as exc:
            raise ProxyAPIError("mihomo API returned invalid JSON") from exc
        except Exception as exc:  # noqa: BLE001
            raise ProxyAPIError(f"Failed to parse mihomo API response: {exc}") from exc


__all__ = ["APIRequest", "MihomoAPI", "ProxyAPIError"]
