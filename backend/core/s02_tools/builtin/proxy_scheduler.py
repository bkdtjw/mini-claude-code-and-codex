from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from .proxy_api import MihomoAPI
from .proxy_api_support import now_text
from .proxy_chain import CHAIN_GROUP_NAME
from .proxy_scheduler_llm import decide_all_timeout_with_llm
from .proxy_scheduler_models import LLMCallback, SchedulerDecision, SchedulerError
from .proxy_scheduler_runtime import (
    ensure_chain_group,
    format_current,
    format_runtime,
    load_current_node,
)
from .proxy_scheduler_support import decide, format_scheduler_status


class ChainScheduler:
    """智能链式代理调度引擎。"""

    def __init__(
        self,
        api_url: str,
        api_secret: str,
        config_path: str,
        custom_nodes_path: str,
        interval: int = 60,
        timeout: int = 5000,
        switch_cooldown: int = 30,
        min_improvement: int = 30,
        llm_callback: LLMCallback | None = None,
    ) -> None:
        self._api = MihomoAPI(api_url, api_secret)
        self._config_path = config_path
        self._custom_nodes_path = custom_nodes_path
        self._interval = interval
        self._timeout = timeout
        self._switch_cooldown = switch_cooldown
        self._min_improvement = min_improvement
        self._llm = llm_callback
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._history: list[dict[str, Any]] = []
        self._current_node = ""
        self._current_delay = 0
        self._last_test_time = ""
        self._consecutive_all_timeout = 0
        self._llm_call_count = 0
        self._start_time: datetime | None = None
    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()
    async def start(self) -> str:
        try:
            if self.is_running:
                return await self.status()
            chain_count = await self._ensure_chain_group()
            self._current_node = await self._load_current_node()
            await self._test_and_decide()
            self._running = True
            self._start_time = datetime.now()
            self._task = asyncio.create_task(self._loop())
            return "\n".join(
                [
                    "调度引擎已启动",
                    f"测速间隔: {self._interval} 秒",
                    f"LLM 智能层: {'已启用' if self._llm else '未启用'}",
                    f"Chain 组节点: {chain_count} 个",
                    f"当前最优: {format_current(self._current_node, self._current_delay)}",
                ]
            )
        except Exception as exc:
            raise SchedulerError(f"启动调度引擎失败: {exc}") from exc
    async def stop(self) -> str:
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
            return "\n".join(
                [
                    "调度引擎已停止",
                    f"运行时长: {format_runtime(self._start_time)}",
                    f"切换次数: {len(self._history)} 次",
                    f"LLM 调用次数: {self._llm_call_count} 次",
                ]
            )
        except Exception as exc:
            raise SchedulerError(f"停止调度引擎失败: {exc}") from exc
    async def status(self) -> str:
        try:
            return format_scheduler_status(
                self.is_running,
                format_current(self._current_node, self._current_delay),
                self._last_test_time,
                self._interval,
                self._llm is not None,
                self._llm_call_count,
                self._history,
            )
        except Exception as exc:
            raise SchedulerError(f"查询调度引擎状态失败: {exc}") from exc
    async def _loop(self) -> None:
        try:
            while self._running:
                await self._test_and_decide()
                wait_seconds = 15 if self._consecutive_all_timeout in {1, 2} else self._interval
                await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            return
        except Exception:
            self._running = False
    async def _test_and_decide(self) -> SchedulerDecision:
        try:
            result = await self._api.test_group_delay(CHAIN_GROUP_NAME, timeout=self._timeout)
            self._last_test_time = result.timestamp or now_text()
            self._current_node = await self._load_current_node() or self._current_node
            is_all_timeout = bool(result.results) and all(
                delay <= 0 for delay in result.results.values()
            )
            self._consecutive_all_timeout = (
                self._consecutive_all_timeout + 1 if is_all_timeout else 0
            )
            decision = (
                await decide_all_timeout_with_llm(
                    self._llm,
                    self._current_node,
                    self._history,
                    result.results,
                )
                if is_all_timeout and self._consecutive_all_timeout == 2 and self._llm is not None
                else await decide(
                    self._current_node,
                    result.results,
                    self._history,
                    self._switch_cooldown,
                    self._min_improvement,
                    self._llm,
                )
            )
            if decision.source == "llm":
                self._llm_call_count += 1
            if decision.should_switch and decision.target:
                await self._switch(decision)
            else:
                self._current_delay = int(
                    result.results.get(self._current_node, decision.current_delay)
                )
            return decision
        except Exception as exc:
            raise SchedulerError(f"测速与决策失败: {exc}") from exc
    async def _ensure_chain_group(self) -> int:
        try:
            return await ensure_chain_group(self._api, self._config_path, self._custom_nodes_path)
        except Exception as exc:
            raise SchedulerError(f"确保 Chain 组失败: {exc}") from exc
    async def _load_current_node(self) -> str:
        try:
            return await load_current_node(self._api)
        except Exception:
            return ""
    async def _switch(self, decision: SchedulerDecision) -> None:
        try:
            if not await self._api.switch_proxy(CHAIN_GROUP_NAME, decision.target):
                raise SchedulerError(f"切换 Chain 节点失败: {decision.target}")
            previous = self._current_node
            self._current_node = decision.target
            self._current_delay = decision.target_delay
            if previous and previous != decision.target:
                self._record(
                    previous,
                    decision.target,
                    decision.reason,
                    decision.target_delay,
                    decision.source,
                )
        except Exception as exc:
            raise SchedulerError(f"执行切换失败: {exc}") from exc
    def _record(self, from_node: str, to_node: str, reason: str, delay: int, source: str) -> None:
        self._history.append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "from": from_node,
                "to": to_node,
                "reason": reason,
                "delay": delay,
                "source": source,
            }
        )
        self._history = self._history[-50:]
__all__ = ["ChainScheduler"]
