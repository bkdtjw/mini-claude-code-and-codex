"""基于北京时间的 Twitter-飞书定时调度引擎。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .twitter_feishu_job import (
    FeishuSendFn,
    LLMCallback,
    TwitterSearchFn,
    execute_job,
)
from .twitter_feishu_models import (
    JobExecutionRecord,
    SchedulerJobConfig,
    SchedulerState,
)

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


class TwitterFeishuSchedulerError(Exception):
    """调度器错误。"""


class TwitterFeishuScheduler:
    """每日定时执行 Twitter 搜索→LLM 总结→飞书推送。"""

    def __init__(
        self,
        config: SchedulerJobConfig,
        search_fn: TwitterSearchFn,
        llm_fn: LLMCallback | None,
        feishu_fn: FeishuSendFn,
    ) -> None:
        self._config = config
        self._search_fn = search_fn
        self._llm_fn = llm_fn
        self._feishu_fn = feishu_fn
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._history: list[JobExecutionRecord] = []
        self._total_executions = 0
        self._total_failures = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> str:
        """启动调度器。"""
        try:
            if self.is_running:
                return self._format_status("调度器已在运行中")
            self._running = True
            self._task = asyncio.create_task(self._loop())
            return self._format_status("调度器已启动")
        except Exception as exc:
            raise TwitterFeishuSchedulerError(f"启动调度器失败: {exc}") from exc

    async def stop(self) -> str:
        """停止调度器。"""
        try:
            if self._task and not self._task.done():
                self._running = False
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
            self._running = False
            return self._format_status("调度器已停止")
        except Exception as exc:
            raise TwitterFeishuSchedulerError(f"停止调度器失败: {exc}") from exc

    async def run_now(self) -> str:
        """立即执行一次任务（不影响定时调度）。"""
        try:
            record = await execute_job(
                self._config, self._search_fn, self._llm_fn, self._feishu_fn,
            )
            self._record_result(record)
            return _format_execution_result(record)
        except Exception as exc:
            raise TwitterFeishuSchedulerError(f"手动执行失败: {exc}") from exc

    def status(self) -> str:
        """获取调度器状态。"""
        return self._format_status("运行中" if self.is_running else "已停止")

    def get_state(self) -> SchedulerState:
        """获取结构化状态快照。"""
        return SchedulerState(
            is_running=self.is_running,
            job_config=self._config,
            next_run_beijing=_next_run_text(self._config) if self.is_running else "",
            last_execution=self._history[-1] if self._history else None,
            total_executions=self._total_executions,
            total_failures=self._total_failures,
        )

    async def _loop(self) -> None:
        """主循环：计算下次执行时间，sleep 等待，执行任务。"""
        try:
            while self._running:
                sleep_seconds = _seconds_until_next_run(self._config)
                logger.info("Next run in %.0f seconds", sleep_seconds)
                await asyncio.sleep(sleep_seconds)
                if not self._running:
                    break
                record = await execute_job(
                    self._config, self._search_fn, self._llm_fn, self._feishu_fn,
                )
                self._record_result(record)
                logger.info("Job %s completed: %s", record.job_id, record.status)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("Scheduler loop crashed: %s", exc)
            self._running = False

    def _record_result(self, record: JobExecutionRecord) -> None:
        self._total_executions += 1
        if record.status == "failed":
            self._total_failures += 1
        self._history.append(record)
        self._history = self._history[-50:]

    def _format_status(self, headline: str) -> str:
        now_bj = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            headline,
            f"当前北京时间: {now_bj}",
            f"定时执行: 每天 {self._config.cron_hour:02d}:{self._config.cron_minute:02d} 北京时间",
            f"搜索目标数: {len(self._config.targets)}",
            f"累计执行: {self._total_executions} 次 (失败 {self._total_failures} 次)",
        ]
        if self.is_running:
            lines.append(f"下次执行: {_next_run_text(self._config)}")
        if self._history:
            last = self._history[-1]
            lines.append(f"上次执行: {last.executed_at.strftime('%Y-%m-%d %H:%M')} [{last.status}]")
        return "\n".join(lines)


def _seconds_until_next_run(config: SchedulerJobConfig) -> float:
    """计算距离下次执行的秒数（北京时间）。"""
    now = datetime.now(BEIJING_TZ)
    target = now.replace(
        hour=config.cron_hour, minute=config.cron_minute, second=0, microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    delta = (target - now).total_seconds()
    return max(delta, 1.0)


def _next_run_text(config: SchedulerJobConfig) -> str:
    now = datetime.now(BEIJING_TZ)
    target = now.replace(
        hour=config.cron_hour, minute=config.cron_minute, second=0, microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%d %H:%M 北京时间")


def _format_execution_result(record: JobExecutionRecord) -> str:
    lines = [
        f"任务执行完成 [{record.status}]",
        f"搜索目标: {record.targets_searched} 个",
        f"发现推文: {record.tweets_found} 条",
        f"总结长度: {record.summary_length} 字符",
        f"飞书推送: {'成功' if record.feishu_sent else '未发送'}",
        f"耗时: {record.duration_seconds}s",
    ]
    if record.error:
        lines.append(f"错误: {record.error}")
    return "\n".join(lines)


__all__ = [
    "TwitterFeishuScheduler",
    "TwitterFeishuSchedulerError",
]
