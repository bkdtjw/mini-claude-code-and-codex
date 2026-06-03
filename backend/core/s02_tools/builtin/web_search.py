from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import AliasChoices, BaseModel, Field, ValidationError, field_validator

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

ZHIPU_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
SEARCH_TIMEOUT_SECONDS = 30.0
MAX_RESULTS_DEFAULT = 5
MAX_FORMATTED_OUTPUT_CHARS = 11000

SearchRecency = Literal["noLimit", "day", "week", "month"]


class WebSearchToolError(Exception):
    pass


class WebSearchArgs(BaseModel):
    query: str
    count: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=20)
    time_filter: SearchRecency = "noLimit"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("搜索关键词不能为空")
        return query


class WebSearchResultItem(BaseModel):
    title: str = ""
    link: str = ""
    snippet: str = Field(default="", validation_alias=AliasChoices("snippet", "content"))
    media: str = ""
    publish_time: str = Field(
        default="",
        validation_alias=AliasChoices("publish_time", "publish_date"),
    )

    @field_validator("title", "link", "snippet", "media", "publish_time", mode="before")
    @classmethod
    def stringify_value(cls, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list | dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()


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
                "time_filter": {
                    "type": "string",
                    "description": "时间过滤，默认 noLimit",
                    "enum": ["noLimit", "day", "week", "month"],
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
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, trust_env=False) as client:
                response = await client.post(
                    ZHIPU_SEARCH_URL,
                    headers={
                        "Authorization": f"Bearer {resolved_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=_build_request_body(params),
                )
            response.raise_for_status()
            payload = _load_json(response)
            results = _extract_search_results(payload)
            if not results:
                return ToolResult(output=f"未找到搜索结果：{params.query}", is_error=True)
            return ToolResult(output=_format_results(params, results))
        except httpx.TimeoutException:
            return ToolResult(output="智谱 Web Search 请求超时，请稍后重试。", is_error=True)
        except httpx.HTTPStatusError as exc:
            detail = _response_error_detail(exc.response)
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

def _build_request_body(params: WebSearchArgs) -> dict[str, Any]:
    return {
        "search_engine": "search_pro",
        "search_query": params.query,
        "count": params.count,
        "search_recency_filter": params.time_filter,
        "content_size": "medium",
    }

def _load_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise WebSearchToolError("智谱 Web Search 响应不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise WebSearchToolError("智谱 Web Search 响应格式不正确")
    error = payload.get("error")
    if error:
        detail = json.dumps(error, ensure_ascii=False) if isinstance(error, dict) else str(error)
        raise WebSearchToolError(f"智谱 Web Search API 错误：{detail[:500]}")
    return payload

def _extract_search_results(payload: dict[str, Any]) -> list[WebSearchResultItem]:
    candidate = payload.get("search_result")
    if not isinstance(candidate, list):
        data = payload.get("data")
        if isinstance(data, dict):
            candidate = data.get("search_result")
    if not isinstance(candidate, list):
        raise WebSearchToolError("智谱 Web Search 响应缺少 search_result")
    valid_items = (item for item in candidate if isinstance(item, dict))
    return [WebSearchResultItem.model_validate(item) for item in valid_items]

def _format_results(params: WebSearchArgs, results: list[WebSearchResultItem]) -> str:
    sections = [f'WebSearch 搜索结果: "{params.query}" (共 {len(results)} 条)']
    for index, item in enumerate(results, start=1):
        section = _format_item(index, item)
        current = "\n".join(sections)
        if len(current) + len(section) + 1 > MAX_FORMATTED_OUTPUT_CHARS:
            remaining = len(results) - index + 1
            sections.append(f"\n后续 {remaining} 条结果省略以控制输出长度。")
            break
        sections.append(section)
    return "\n".join(sections)

def _format_item(index: int, item: WebSearchResultItem) -> str:
    lines = [
        "",
        f"{index}. {_clip(item.title, 140) or '无标题'}",
        f"   URL: {_clip(item.link, 240) or '未知'}",
        f"   摘要: {_clip(item.snippet, 260) or '无摘要'}",
    ]
    if item.publish_time:
        lines.append(f"   发布时间: {_clip(item.publish_time, 80)}")
    if item.media:
        lines.append(f"   来源媒体: {_clip(item.media, 120)}")
    return "\n".join(lines)

def _clip(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."

def _response_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:500]
        return json.dumps(payload, ensure_ascii=False)[:500]
    return str(payload)[:500]
