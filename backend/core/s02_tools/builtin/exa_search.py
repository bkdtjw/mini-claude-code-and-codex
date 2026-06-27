from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from backend.common.logging import get_logger

EXA_SEARCH_URL = "https://api.exa.ai/search"
logger = get_logger(component="exa_search")


class ExaSearchError(Exception):
    """Exa search error."""


class ExaResult(BaseModel):
    title: str = ""
    url: str = ""
    published_date: str = ""
    author: str = ""
    highlights: list[str] = Field(default_factory=list)
    text: str = ""


class ExaSearchRequest(BaseModel):
    query: str
    api_key: str
    start_published: datetime | None = None
    end_published: datetime | None = None
    num_results: int = Field(default=5, ge=1, le=25)
    user_location: str = "US"
    proxy_url: str = ""


async def exa_search(request: ExaSearchRequest) -> list[ExaResult]:
    try:
        if not request.api_key.strip():
            raise ExaSearchError("缺少 Exa API key，请检查 EXA_API_KEY 配置")
        async with httpx.AsyncClient(
            timeout=20.0,
            proxy=request.proxy_url or None,
            trust_env=False,
        ) as client:
            response = await client.post(
                EXA_SEARCH_URL,
                headers={"x-api-key": request.api_key, "content-type": "application/json"},
                json=_build_body(request),
            )
            response.raise_for_status()
            payload = response.json()
        return _parse_results(payload)
    except ExaSearchError:
        raise
    except httpx.HTTPStatusError as exc:
        raise ExaSearchError(_translate_http_error(exc)) from exc
    except httpx.HTTPError as exc:
        proxy_hint = request.proxy_url or "direct"
        raise ExaSearchError(
            f"Exa 搜索失败：网络请求失败 [{exc.__class__.__name__}] {exc}（proxy={proxy_hint}）"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("exa_search_failed", error=str(exc))
        raise ExaSearchError(f"Exa 搜索失败：{exc}") from exc


def _build_body(request: ExaSearchRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "query": request.query,
        "type": "auto",
        "numResults": request.num_results,
        "userLocation": request.user_location,
        "contents": {"highlights": True, "maxAgeHours": 0},
    }
    if request.start_published is not None:
        body["startPublishedDate"] = _to_z(request.start_published)
    if request.end_published is not None:
        body["endPublishedDate"] = _to_z(request.end_published)
    return body


def _to_z(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_results(payload: dict[str, Any]) -> list[ExaResult]:
    results: list[ExaResult] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        results.append(
            ExaResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                published_date=str(item.get("publishedDate") or ""),
                author=str(item.get("author") or ""),
                highlights=[str(h) for h in (item.get("highlights") or []) if h],
                text=str(item.get("text") or ""),
            )
        )
    return results


def _translate_http_error(exc: httpx.HTTPStatusError) -> str:
    code = exc.response.status_code if exc.response is not None else 0
    if code in {401, 403}:
        return "Exa API key 无效或无权限，请检查 EXA_API_KEY 配置"
    if code == 429:
        return "Exa 速率限制，请稍后再试"
    return f"Exa 搜索失败：HTTP {code}"


__all__ = ["ExaResult", "ExaSearchError", "ExaSearchRequest", "exa_search"]
