from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.common.logging import get_logger
from backend.core.task_queue_consumer import SubAgentConsumerContext, consume_next_sub_agent_task
from backend.core.task_queue_stats import get_task_queue_snapshot

logger = get_logger(component="sub_worker_scaler")


@dataclass(frozen=True)
class WorkerPoolConfig:
    default_concurrency: int
    max_concurrency: int
    idle_seconds: float = 30.0
    poll_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.default_concurrency < 1:
            raise ValueError("default_concurrency must be >= 1")
        if self.max_concurrency < self.default_concurrency:
            raise ValueError("max_concurrency must be >= default_concurrency")


class WorkerPoolController:
    def __init__(
        self,
        context: SubAgentConsumerContext,
        shutdown_event: asyncio.Event,
        config: WorkerPoolConfig,
    ) -> None:
        self._context = context
        self._shutdown_event = shutdown_event
        self._config = config
        self._consumers: list[asyncio.Task[None]] = []
        self._retired: list[asyncio.Task[None]] = []
        self._idle_since = 0.0

    def start(self) -> list[asyncio.Task[None]]:
        return [asyncio.create_task(self.run(), name="sub-worker-scaler")]

    async def run(self) -> None:
        self._scale_to(self._config.default_concurrency)
        try:
            while not self._shutdown_event.is_set():
                await self._adjust_once()
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._config.poll_seconds,
                    )
                except TimeoutError:
                    continue
        finally:
            await self._cancel_consumers()

    async def _adjust_once(self) -> None:
        snapshot = await get_task_queue_snapshot(self._context.queue)
        target = self._target_concurrency(snapshot.unfinished)
        if target > len(self._consumers):
            self._scale_to(target)
            self._idle_since = 0.0
            return
        if snapshot.unfinished > 0:
            self._idle_since = 0.0
            return
        loop_time = asyncio.get_running_loop().time()
        self._idle_since = self._idle_since or loop_time
        if loop_time - self._idle_since >= self._config.idle_seconds:
            self._scale_to(self._config.default_concurrency)

    def _target_concurrency(self, unfinished: int) -> int:
        if unfinished <= self._config.default_concurrency:
            return self._config.default_concurrency
        return min(self._config.max_concurrency, unfinished)

    def _scale_to(self, target: int) -> None:
        current = len(self._consumers)
        if target > current:
            for index in range(current + 1, target + 1):
                self._consumers.append(
                    asyncio.create_task(
                        self._consume_loop(),
                        name=f"sub-worker-consumer-{index}",
                    )
                )
            logger.info("sub_worker_scaled", current=current, target=target)
            return
        if target < current:
            retiring = self._consumers[target:]
            self._consumers = self._consumers[:target]
            for task in retiring:
                task.cancel()
            self._retired.extend(retiring)
            logger.info("sub_worker_scaled", current=current, target=target)

    async def _cancel_consumers(self) -> None:
        retiring = [*self._retired, *self._consumers]
        self._retired, self._consumers = [], []
        for task in retiring:
            task.cancel()
        if retiring:
            await asyncio.gather(*retiring, return_exceptions=True)

    async def _consume_loop(self) -> None:
        logger.info("task_queue_consumer_started", namespace=self._context.queue.namespace)
        while not self._shutdown_event.is_set():
            try:
                processed = await consume_next_sub_agent_task(self._context)
                if not processed:
                    await self._wait_for_shutdown(1.0)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "consumer_loop_error",
                    namespace=self._context.queue.namespace,
                    error=str(exc),
                )
                await self._wait_for_shutdown(1.0)

    async def _wait_for_shutdown(self, delay_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay_seconds)
        except TimeoutError:
            return


__all__ = ["WorkerPoolConfig", "WorkerPoolController"]
