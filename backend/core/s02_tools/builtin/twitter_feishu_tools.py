"""Twitter-飞书定时任务的 Tool 注册。"""

from __future__ import annotations

import json
from typing import Any

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .twitter_feishu_models import SchedulerJobConfig, TwitterSearchTarget
from .twitter_feishu_scheduler import TwitterFeishuScheduler


def create_twitter_feishu_scheduler_tool(
    scheduler: TwitterFeishuScheduler,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    """创建 Twitter-飞书定时调度工具。"""
    definition = ToolDefinition(
        name="twitter_feishu_scheduler",
        description=(
            "管理 Twitter-飞书定时推送任务。"
            "支持 start（启动定时）、stop（停止）、run_now（立即执行）、status（查看状态）。"
        ),
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "action": {
                    "type": "string",
                    "description": "操作: start / stop / run_now / status",
                    "enum": ["start", "stop", "run_now", "status"],
                },
            },
            required=["action"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            action = str(args.get("action", "")).strip()
            if action == "start":
                output = await scheduler.start()
            elif action == "stop":
                output = await scheduler.stop()
            elif action == "run_now":
                output = await scheduler.run_now()
            elif action == "status":
                output = scheduler.status()
            else:
                return ToolResult(
                    output=f"未知操作: {action}，可用操作: start / stop / run_now / status",
                    is_error=True,
                )
            return ToolResult(output=output)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def build_default_config(
    job_id: str = "twitter_daily",
    cron_hour: int = 7,
    cron_minute: int = 0,
    targets_json: str = "",
    feishu_webhook_url: str = "",
    feishu_secret: str = "",
) -> SchedulerJobConfig:
    """从环境变量或参数构建默认配置。"""
    targets = _parse_targets(targets_json)
    if not targets:
        targets = [
            TwitterSearchTarget(
                name="AI & LLM",
                query="AI agent OR LLM OR GPT",
                max_results=20,
                days=1,
            ),
        ]
    return SchedulerJobConfig(
        job_id=job_id,
        cron_hour=cron_hour,
        cron_minute=cron_minute,
        targets=targets,
        feishu_webhook_url=feishu_webhook_url,
        feishu_secret=feishu_secret,
    )


def _parse_targets(targets_json: str) -> list[TwitterSearchTarget]:
    """从 JSON 字符串解析搜索目标列表。"""
    if not targets_json.strip():
        return []
    try:
        raw = json.loads(targets_json)
        if not isinstance(raw, list):
            return []
        return [TwitterSearchTarget.model_validate(item) for item in raw]
    except (json.JSONDecodeError, ValueError):
        return []


__all__ = [
    "build_default_config",
    "create_twitter_feishu_scheduler_tool",
]
