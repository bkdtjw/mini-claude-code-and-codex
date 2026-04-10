"""Twitter 搜索 → LLM 总结 → 飞书推送 的任务执行器。"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from .twitter_feishu_models import (
    JobExecutionRecord,
    SchedulerJobConfig,
    TwitterSearchTarget,
)
from .twitter_feishu_prompt import build_summary_prompt

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

LLMCallback = Callable[[str, str], Awaitable[str]]
"""(system_prompt, user_prompt) -> summary"""

TwitterSearchFn = Callable[[str, int, int, str], Awaitable[str]]
"""(query, max_results, days, search_type) -> formatted_results"""

FeishuSendFn = Callable[[str, str], Awaitable[bool]]
"""(title, content) -> success"""


class TwitterFeishuJobError(Exception):
    """任务执行错误。"""


async def execute_job(
    config: SchedulerJobConfig,
    search_fn: TwitterSearchFn,
    llm_fn: LLMCallback | None,
    feishu_fn: FeishuSendFn,
) -> JobExecutionRecord:
    """执行一次完整的 搜索→总结→推送 流程。"""
    record = JobExecutionRecord(job_id=config.job_id, status="running")
    start = time.monotonic()
    try:
        search_results = await _search_all_targets(config.targets, search_fn, record)
        if not search_results.strip():
            record.status = "success"
            record.error = "所有搜索目标均无结果"
            record.duration_seconds = time.monotonic() - start
            return record

        now_beijing = datetime.now(BEIJING_TZ)
        report_date = now_beijing.strftime("%Y-%m-%d")
        report_title = f"Twitter 每日简报"

        content = await _summarize(
            report_title, report_date, search_results, llm_fn,
        )
        record.summary_length = len(content)

        title = f"📰 {report_title} — {report_date}"
        sent = await feishu_fn(title, content)
        record.feishu_sent = sent
        record.status = "success"
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)[:500]
        logger.exception("Twitter-Feishu job failed: %s", exc)
    finally:
        record.duration_seconds = round(time.monotonic() - start, 2)
    return record


async def _search_all_targets(
    targets: list[TwitterSearchTarget],
    search_fn: TwitterSearchFn,
    record: JobExecutionRecord,
) -> str:
    """依次搜索所有目标，拼接结果。"""
    sections: list[str] = []
    for target in targets:
        try:
            result = await search_fn(
                target.query, target.max_results, target.days, target.search_type,
            )
            if result.strip():
                sections.append(f"## 搜索目标：{target.name}\n\n{result}")
                record.tweets_found += result.count("\n@") + result.count("\n1.")
            record.targets_searched += 1
        except Exception as exc:
            logger.warning("Search target '%s' failed: %s", target.name, exc)
            sections.append(f"## 搜索目标：{target.name}\n\n⚠️ 搜索失败：{exc}")
    return "\n\n---\n\n".join(sections)


async def _summarize(
    report_title: str,
    report_date: str,
    search_results: str,
    llm_fn: LLMCallback | None,
) -> str:
    """使用 LLM 生成总结，若无 LLM 则直接返回原始数据。"""
    if llm_fn is None:
        return f"# {report_title} — {report_date}\n\n{search_results}"
    system_prompt, user_prompt = build_summary_prompt(
        report_title, report_date, search_results,
    )
    try:
        return await llm_fn(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("LLM summary failed, fallback to raw: %s", exc)
        return f"# {report_title} — {report_date}\n\n> ⚠️ LLM 总结失败，以下为原始数据\n\n{search_results}"


__all__ = [
    "FeishuSendFn",
    "LLMCallback",
    "TwitterFeishuJobError",
    "TwitterSearchFn",
    "execute_job",
]
