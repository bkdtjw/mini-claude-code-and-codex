from __future__ import annotations

import json
import re
from typing import Any, Literal

import httpx
from pydantic import AliasChoices, BaseModel, Field, field_validator

MAX_FORMATTED_OUTPUT_CHARS = 11000
MIN_RESULTS = 5
MAX_WIDEN_STEPS = 2

# 智谱实测：只有 oneXxx 真生效，裸 day/week/month 会被静默忽略（当 noLimit）。
SearchRecency = Literal["oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"]
Freshness = Literal["breaking", "recent", "general", "historical"]

FRESHNESS_TO_RECENCY: dict[str, SearchRecency] = {
    "breaking": "oneDay",
    "recent": "oneWeek",
    "general": "oneMonth",
    "historical": "noLimit",
}
# 向后兼容：旧调用的 day/week/month（失效值）映射到真正生效的 oneXxx。
LEGACY_TIME_FILTER: dict[str, SearchRecency] = {
    "day": "oneDay", "week": "oneWeek", "month": "oneMonth", "year": "oneYear",
    "oneDay": "oneDay", "oneWeek": "oneWeek", "oneMonth": "oneMonth",
    "oneYear": "oneYear", "noLimit": "noLimit",
}
WIDEN_LADDER: list[SearchRecency] = ["oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"]

_BREAKING_HINTS = ("今天", "刚刚", "现在", "实时", "breaking", "just now", "right now")
_HISTORICAL_HINTS = ("历史", "沿革", "起源", "由来", "history", "origin", "evolution")
_RECENT_HINTS = ("最新", "近期", "本周", "这几天", "latest", "recent", "newest", "update")
_ENTITY_HINT = re.compile(r"[a-z]{2,}[-\s]?\d")  # gpt5 / gpt-5 / claude 4 / fable5 / llama3


class WebSearchToolError(Exception):
    pass


class WebSearchResultItem(BaseModel):
    title: str = ""
    link: str = ""
    snippet: str = Field(default="", validation_alias=AliasChoices("snippet", "content"))
    media: str = ""
    publish_time: str = Field(
        default="", validation_alias=AliasChoices("publish_time", "publish_date")
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


def infer_freshness(query: str) -> Freshness:
    q = f" {query.lower()} "
    if any(hint in q for hint in _BREAKING_HINTS):
        return "breaking"
    if any(hint in q for hint in _HISTORICAL_HINTS):
        return "historical"
    if any(hint in q for hint in _RECENT_HINTS) or _ENTITY_HINT.search(q):
        return "recent"
    return "general"


def resolve_recency(freshness: str | None, time_filter: str | None, query: str) -> SearchRecency:
    if freshness:
        return FRESHNESS_TO_RECENCY.get(freshness, "oneMonth")
    if time_filter:
        return LEGACY_TIME_FILTER.get(time_filter, "noLimit")
    return FRESHNESS_TO_RECENCY[infer_freshness(query)]


def widen_path(start: SearchRecency) -> list[SearchRecency]:
    if start not in WIDEN_LADDER:
        return ["noLimit"]
    index = WIDEN_LADDER.index(start)
    return WIDEN_LADDER[index : index + 1 + MAX_WIDEN_STEPS]


def load_json(response: httpx.Response) -> dict[str, Any]:
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


def extract_search_results(payload: dict[str, Any]) -> list[WebSearchResultItem]:
    candidate = payload.get("search_result")
    if not isinstance(candidate, list):
        data = payload.get("data")
        candidate = data.get("search_result") if isinstance(data, dict) else None
    if not isinstance(candidate, list):
        return []  # 无结果（不抛错），让上层可以扩窗
    return [WebSearchResultItem.model_validate(it) for it in candidate if isinstance(it, dict)]


def format_results(
    query: str, results: list[WebSearchResultItem], recency: str, widened: bool
) -> str:
    note = "，已自动放宽" if widened else ""
    sections = [f'WebSearch 搜索结果: "{query}" (共 {len(results)} 条, 时间窗={recency}{note})']
    for index, item in enumerate(results, start=1):
        section = _format_item(index, item)
        if len("\n".join(sections)) + len(section) + 1 > MAX_FORMATTED_OUTPUT_CHARS:
            sections.append(f"\n后续 {len(results) - index + 1} 条结果省略以控制输出长度。")
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
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 3]}..."


def response_error_detail(response: httpx.Response) -> str:
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


__all__ = [
    "Freshness",
    "MIN_RESULTS",
    "SearchRecency",
    "WebSearchResultItem",
    "WebSearchToolError",
    "extract_search_results",
    "format_results",
    "infer_freshness",
    "load_json",
    "resolve_recency",
    "response_error_detail",
    "widen_path",
]
