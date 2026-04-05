from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .proxy_auto_start import _ensure_mihomo_running
from .proxy_scheduler import ChainScheduler
from .proxy_scheduler_models import LLMCallback

_scheduler: ChainScheduler | None = None


class SchedulerToolArgs(BaseModel):
    action: Literal["start", "stop", "status"]
    interval: int = Field(default=60, ge=5, le=3600)
    timeout: int = Field(default=5000, ge=100, le=60000)
    cooldown: int = Field(default=30, ge=0, le=3600)
    min_improvement: int = Field(default=30, ge=0, le=10000)


def create_proxy_scheduler_tool(
    api_url: str,
    api_secret: str,
    config_path: str,
    custom_nodes_path: str,
    llm_callback: LLMCallback | None = None,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_scheduler",
        description="管理智能链式代理调度引擎（自动测速并切换最优链式节点，支持 LLM 智能决策）",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "action": {"type": "string", "description": "start | stop | status"},
                "interval": {"type": "integer", "description": "测速间隔秒数，默认 60"},
                "timeout": {"type": "integer", "description": "节点超时毫秒，默认 5000"},
                "cooldown": {"type": "integer", "description": "切换冷却秒数，默认 30"},
                "min_improvement": {"type": "integer", "description": "最小改善阈值 ms，默认 30"},
            },
            required=["action"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        global _scheduler
        try:
            params = SchedulerToolArgs.model_validate(args)
            if params.action == "start":
                err = await _ensure_mihomo_running(api_url, api_secret)
                if err:
                    return ToolResult(output=err, is_error=True)
                if _scheduler is None or not _scheduler.is_running:
                    _scheduler = ChainScheduler(
                        api_url=api_url,
                        api_secret=api_secret,
                        config_path=config_path,
                        custom_nodes_path=custom_nodes_path,
                        interval=params.interval,
                        timeout=params.timeout,
                        switch_cooldown=params.cooldown,
                        min_improvement=params.min_improvement,
                        llm_callback=llm_callback,
                    )
                return ToolResult(output=await _scheduler.start())
            if _scheduler is None:
                return ToolResult(output="调度引擎未启动")
            output = await (_scheduler.stop() if params.action == "stop" else _scheduler.status())
            return ToolResult(output=output)
        except ValidationError as exc:
            return ToolResult(output=exc.errors()[0].get("msg", "参数错误"), is_error=True)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = ["create_proxy_scheduler_tool"]
