from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.common.logging import get_logger
from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .collect_and_process_support import (
    CollectAndProcessPipelineError, PipelineConfig, PipelineResult, RawTweet, RawVideo,
    TaskMemory, map_video, map_x_post, process_raw_data,
)
from .x_client import XClientConfig, XRateLimitError, XSearchOptions, search_x_posts
from .youtube_client import YouTubeSearchRequest, search_videos

DEFAULT_TASK_ID = "ai_morning_report"
DEFAULT_TASK_STATE_DIR = "/app/data/task_state"
DEFAULT_TIMEOUT_SECONDS = 120.0

logger = get_logger(component="collect_and_process")
class CollectAndProcessToolError(Exception):
    """Collect-and-process tool error."""

class CollectAndProcessConfig(BaseModel):
    x_config: XClientConfig
    youtube_api_key: str = ""
    youtube_proxy_url: str = ""
    timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0, le=600)
    task_state_dir: str = DEFAULT_TASK_STATE_DIR
    pipeline_config: PipelineConfig = Field(default_factory=PipelineConfig)

class CollectAndProcessArgs(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=20)
    max_results_per_keyword: int = Field(default=30, ge=1, le=50)
    days: int = Field(default=1, ge=1, le=365)
    include_youtube: bool = True
    task_id: str = DEFAULT_TASK_ID

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        keywords = [item.strip() for item in value if item.strip()]
        if not keywords:
            raise ValueError("搜索关键词不能为空")
        return list(dict.fromkeys(keywords))

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        task_id = value.strip() or DEFAULT_TASK_ID
        if not all(char.isalnum() or char in {"_", "-"} for char in task_id):
            raise ValueError("task_id 只能包含字母、数字、下划线或连字符")
        return task_id

class CollectRunState(BaseModel):
    params: CollectAndProcessArgs
    config: CollectAndProcessConfig
    memory: TaskMemory
    warnings: list[str] = Field(default_factory=list)

def create_collect_and_process_tool(config: CollectAndProcessConfig) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="collect_and_process",
        description="Collect X/Twitter posts and optional YouTube videos, then return evidence cards.",
        category="search",
        parameters=ToolParameterSchema(
            properties={
                "keywords": {"type": "array", "items": {"type": "string"}},
                "max_results_per_keyword": {"type": "integer", "description": "Default 30, max 50"},
                "days": {"type": "integer", "description": "Search window in days, default 1"},
                "include_youtube": {"type": "boolean", "description": "Search YouTube too"},
                "task_id": {"type": "string", "description": "Task memory id"},
            },
            required=["keywords"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            params = _parse_args(args)
            output = await asyncio.wait_for(_collect_and_process(params, config), timeout=config.timeout_seconds)
            return ToolResult(output=output)
        except asyncio.TimeoutError:
            return ToolResult(output=f"collect_and_process 超时：超过 {config.timeout_seconds:.0f} 秒", is_error=True)
        except CollectAndProcessToolError as exc:
            return ToolResult(output=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"collect_and_process 失败：{exc}", is_error=True)

    return definition, execute

def _parse_args(args: dict[str, object]) -> CollectAndProcessArgs:
    try:
        return CollectAndProcessArgs.model_validate(args)
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "参数不合法")
        raise CollectAndProcessToolError(f"参数错误：{message}") from exc

async def _collect_and_process(params: CollectAndProcessArgs, config: CollectAndProcessConfig) -> str:
    try:
        memory = _load_memory(config, params.task_id)
        state = CollectRunState(params=params, config=config, memory=memory)
        tweets: dict[str, list[RawTweet]] = {}
        for keyword in params.keywords:
            tweets[keyword] = await _search_x_keyword(keyword, state)
        videos = await _search_youtube(state) if params.include_youtube else []
        result = await process_raw_data(tweets, videos, config.pipeline_config, state.memory)
        _save_memory(state, result)
        return _append_warnings(result.evidence_text, state.warnings, config.pipeline_config.max_output_chars)
    except CollectAndProcessPipelineError as exc:
        raise CollectAndProcessToolError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise CollectAndProcessToolError(f"采集处理失败：{exc}") from exc

async def _search_x_keyword(keyword: str, state: CollectRunState) -> list[RawTweet]:
    try:
        params, config = state.params, state.config
        posts = await search_x_posts(
            keyword,
            config.x_config,
            XSearchOptions(max_results=params.max_results_per_keyword, days=params.days, search_type="Latest"),
        )
    except XRateLimitError as exc:
        state.warnings.append(f'X search rate-limited for "{keyword}", using partial results')
        posts = exc.partial_posts
    except Exception as exc:  # noqa: BLE001
        state.warnings.append(f'X search failed for "{keyword}": {exc}')
        return []
    try:
        return [map_x_post(post) for post in posts]
    except CollectAndProcessPipelineError as exc:
        state.warnings.append(f'X mapping failed for "{keyword}": {exc}')
        return []

async def _search_youtube(state: CollectRunState) -> list[RawVideo]:
    try:
        params, config = state.params, state.config
        if not config.youtube_api_key.strip():
            state.warnings.append("YouTube search skipped: YOUTUBE_API_KEY is not configured")
            return []
        videos = await search_videos(
            YouTubeSearchRequest(
                query=" OR ".join(params.keywords), api_key=config.youtube_api_key,
                max_results=min(params.max_results_per_keyword, 20), days=params.days,
                proxy_url=config.youtube_proxy_url,
            )
        )
        return [map_video(video) for video in videos]
    except Exception as exc:  # noqa: BLE001
        state.warnings.append(f"YouTube search failed: {exc}")
        return []

def _load_memory(config: CollectAndProcessConfig, task_id: str) -> TaskMemory:
    path = _state_path(config, task_id)
    if not path.exists():
        return TaskMemory(task_id=task_id)
    try:
        return TaskMemory.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("task_state_read_failed", path=str(path), error=str(exc))
        return TaskMemory(task_id=task_id)

def _save_memory(state: CollectRunState, result: PipelineResult) -> None:
    path = _state_path(state.config, state.params.task_id)
    try:
        urls = list(state.memory.reported_ids)
        for item in result.stats.get("reported_ids", []):
            url = str(item).strip()
            if url and url not in urls:
                urls.append(url)
        signatures = list(state.memory.reported_signatures)
        for item in result.stats.get("reported_signatures", []):
            signature = str(item).strip()
            if signature and signature not in signatures:
                signatures.append(signature)
        path.parent.mkdir(parents=True, exist_ok=True)
        memory = TaskMemory(
            task_id=state.params.task_id, reported_ids=urls[-1000:],
            reported_signatures=signatures[-1000:],
        )
        path.write_text(memory.model_dump_json(indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("task_state_write_failed", path=str(path), error=str(exc))

def _state_path(config: CollectAndProcessConfig, task_id: str) -> Path:
    return Path(config.task_state_dir) / f"{task_id}_urls.json"

def _append_warnings(text: str, warnings: list[str], limit: int) -> str:
    if not warnings:
        return _truncate(text, limit)
    warning_text = "\n".join(f"- {warning}" for warning in warnings)
    return _truncate(f"{text}\n\nCollection warnings:\n{warning_text}", limit)

def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = "\n...[collect_and_process output truncated]..."
    return f"{text[: max(limit - len(marker), 0)].rstrip()}{marker}"
