from __future__ import annotations

import asyncio

from backend.common.types import ToolResult

from .spawner import SpawnParams, SubAgentSpawner


class ResultAggregator:
    """Aggregate multiple sub-agent results."""

    @staticmethod
    async def run_parallel(
        spawner: SubAgentSpawner,
        params_list: list[SpawnParams],
        max_concurrent: int = 3,
    ) -> list[ToolResult]:
        try:
            semaphore = asyncio.Semaphore(max_concurrent)

            async def run_one(params: SpawnParams) -> ToolResult:
                async with semaphore:
                    try:
                        return await spawner.spawn_and_run(params)
                    except Exception as exc:
                        return ToolResult(output=str(exc), is_error=True)

            return list(await asyncio.gather(*(run_one(params) for params in params_list)))
        except Exception as exc:
            return [ToolResult(output=str(exc), is_error=True) for _ in params_list]

    @staticmethod
    def merge_results(results: list[ToolResult]) -> ToolResult:
        outputs = [result.output.strip() for result in results if result.output.strip()]
        return ToolResult(
            output="\n\n---\n\n".join(outputs),
            is_error=any(result.is_error for result in results),
        )


__all__ = ["ResultAggregator"]
