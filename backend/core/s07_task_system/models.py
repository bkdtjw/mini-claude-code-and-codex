from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def _generate_id() -> str:
    return f"task_{secrets.token_hex(4)}"


class NotifyConfig(BaseModel):
    feishu: bool = True
    feishu_webhook_url: str = ""
    feishu_title: str = ""


class OutputConfig(BaseModel):
    save_markdown: bool = False
    output_dir: str = ""


class ScheduledTask(BaseModel):
    id: str = Field(default_factory=_generate_id)
    name: str = ""
    cron: str = "0 * * * *"
    timezone: str = "Asia/Shanghai"
    prompt: str = ""
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    card_scenario: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    last_run_at: datetime | None = None
    last_run_status: str = ""
    last_run_output: str = ""


class TaskStoreData(BaseModel):
    tasks: list[ScheduledTask] = Field(default_factory=list)


__all__ = ["NotifyConfig", "OutputConfig", "ScheduledTask", "TaskStoreData"]
