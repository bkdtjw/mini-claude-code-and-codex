from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from croniter import croniter

from .models import ScheduledTask

_BEIJING = ZoneInfo("Asia/Shanghai")
_SYSTEM_TZ = datetime.now().astimezone().tzinfo or timezone.utc


def resolve_task_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return _BEIJING


def get_scheduled_minute_key(task: ScheduledTask, now: datetime) -> str | None:
    task_tz = resolve_task_timezone(task.timezone)
    local_now = _coerce_datetime(now, task_tz)
    minute_start = local_now.replace(second=0, microsecond=0) - timedelta(seconds=1)
    next_run = croniter(task.cron, minute_start).get_next(datetime)
    expected = local_now.replace(second=0, microsecond=0)
    if next_run != expected:
        return None
    return expected.strftime("%Y%m%d%H%M")


def get_next_run_at(task: ScheduledTask, after: datetime) -> datetime:
    task_tz = resolve_task_timezone(task.timezone)
    localized_after = _coerce_datetime(after, task_tz)
    next_run = croniter(task.cron, localized_after).get_next(datetime)
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=task_tz)
    return next_run.astimezone(timezone.utc)


def _coerce_datetime(value: datetime, target_tz: tzinfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=_SYSTEM_TZ)
    return value.astimezone(target_tz)


__all__ = ["get_next_run_at", "get_scheduled_minute_key", "resolve_task_timezone"]
