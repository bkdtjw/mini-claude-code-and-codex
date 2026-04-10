from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TwitterSearchTarget(BaseModel):
    """单个 Twitter 搜索目标。"""

    name: str = Field(description="目标名称，用于报告标题")
    query: str = Field(description="Twitter 搜索关键词，例如 'AI agent' 或 'from:elonmusk'")
    max_results: int = Field(default=20, ge=1, le=50, description="最多返回推文数")
    days: int = Field(default=1, ge=1, le=30, description="搜索最近 N 天内的推文")
    search_type: str = Field(default="Latest", description="搜索类型: Latest 或 Top")


class SchedulerJobConfig(BaseModel):
    """定时任务配置。"""

    job_id: str = Field(description="任务唯一标识")
    cron_hour: int = Field(default=7, ge=0, le=23, description="每日执行小时（北京时间）")
    cron_minute: int = Field(default=0, ge=0, le=59, description="每日执行分钟（北京时间）")
    targets: list[TwitterSearchTarget] = Field(
        default_factory=list,
        description="搜索目标列表",
    )
    feishu_webhook_url: str = Field(default="", description="飞书 Webhook URL")
    feishu_secret: str = Field(default="", description="飞书 Webhook 签名密钥")
    enabled: bool = Field(default=True, description="是否启用")


JobStatus = Literal["pending", "running", "success", "failed"]


class JobExecutionRecord(BaseModel):
    """任务执行记录。"""

    job_id: str
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    status: JobStatus = "pending"
    targets_searched: int = 0
    tweets_found: int = 0
    summary_length: int = 0
    feishu_sent: bool = False
    error: str = ""
    duration_seconds: float = 0.0


class SchedulerState(BaseModel):
    """调度器运行状态快照。"""

    is_running: bool = False
    job_config: SchedulerJobConfig | None = None
    next_run_beijing: str = ""
    last_execution: JobExecutionRecord | None = None
    total_executions: int = 0
    total_failures: int = 0


__all__ = [
    "JobExecutionRecord",
    "JobStatus",
    "SchedulerJobConfig",
    "SchedulerState",
    "TwitterSearchTarget",
]
