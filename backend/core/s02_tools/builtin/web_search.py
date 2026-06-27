from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .web_search_support import (
    MIN_RESULTS,
    Freshness,
    SearchRecency,
    WebSearchResultItem,
    WebSearchToolError,
    extract_search_results,
    format_results,
    load_json,
    resolve_recency,
    response_error_detail,
    widen_path,
)

ZHIPU_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
SEARCH_TIMEOUT_SECONDS = 30.0
MAX_RESULTS_DEFAULT = 5

_FRESHNESS_GUIDE = (
    "按用户真正需要多新的信息来选，而不是看字面有没有写“最新”：会变的东西"
    "（模型/产品/价格/人事/事件）选 recent；突发或今天选 breaking；一般查询用 general（默认）；"
    "概念/原理/历史用 historical。判不准就别填，系统会按查询自动判，并在结果太少时自动放宽时间窗。"
)


class WebSearchArgs(BaseModel):
    query: str
    count: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=20)
    freshness: Freshness | None = None
    time_filter: str | None = None  # 向后兼容旧调用（day/week/month → oneXxx）

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("搜索关键词不能为空")
        return query


def create_web_search_tool(api_key: str) -> tuple[ToolDefinition, ToolExecuteFn]:
    resolved_api_key = api_key.strip()
    definition = ToolDefinition(
        name="WebSearch",
        description="搜索互联网获取实时信息。输入搜索关键词，返回相关网页的标题、链接和摘要。",
        category="search",
        parameters=ToolParameterSchema(
            properties={
                "query": {"type": "string", "description": "搜索关键词"},
                "count": {"type": "integer", "description": "返回结果数量，1-20，默认 5"},
                "freshness": {
                    "type": "string",
                    "enum": ["breaking", "recent", "general", "historical"],
                    "description": _FRESHNESS_GUIDE,
                },
            },
            required=["query"],
        ),
        side_effect=False,
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            if not resolved_api_key:
                return ToolResult(output="智谱 Web Search API key 未配置", is_error=True)
            params = _parse_args(args)
            ladder = widen_path(resolve_recency(params.freshness, params.time_filter, params.query))
            threshold = min(params.count, MIN_RESULTS)
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, trust_env=False) as client:
                results: list[WebSearchResultItem] = []
                used: SearchRecency = ladder[0]
                for recency in ladder:
                    used = recency
                    results = await _search_once(client, resolved_api_key, params, recency)
                    if len(results) >= threshold:
                        break
            if not results:
                return ToolResult(output=f"未找到搜索结果：{params.query}", is_error=True)
            return ToolResult(output=format_results(params.query, results, used, used != ladder[0]))
        except httpx.TimeoutException:
            return ToolResult(output="智谱 Web Search 请求超时，请稍后重试。", is_error=True)
        except httpx.HTTPStatusError as exc:
            detail = response_error_detail(exc.response)
            output = f"智谱 Web Search API 错误：HTTP {exc.response.status_code}，{detail}"
            return ToolResult(output=output, is_error=True)
        except httpx.RequestError as exc:
            return ToolResult(output=f"智谱 Web Search 网络错误：{exc}", is_error=True)
        except WebSearchToolError as exc:
            return ToolResult(output=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"智谱 Web Search 执行失败：{exc}", is_error=True)

    return definition, execute


def _parse_args(args: dict[str, Any]) -> WebSearchArgs:
    try:
        return WebSearchArgs.model_validate(args)
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "参数不合法")
        raise WebSearchToolError(f"参数错误：{message}") from exc


async def _search_once(
    client: httpx.AsyncClient, api_key: str, params: WebSearchArgs, recency: SearchRecency
) -> list[WebSearchResultItem]:
    response = await client.post(
        ZHIPU_SEARCH_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=_build_request_body(params, recency),
    )
    response.raise_for_status()
    return extract_search_results(load_json(response))


def _build_request_body(params: WebSearchArgs, recency: SearchRecency) -> dict[str, Any]:
    return {
        "search_engine": "search_pro",
        "search_query": params.query,
        "count": params.count,
        "search_recency_filter": recency,
        "content_size": "medium",
    }
