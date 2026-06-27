from __future__ import annotations

import asyncio

import pytest

from backend.core.s04_sub_agents import (
    AgentResultV1,
    StaticDagError,
    StaticDagScheduler,
    TaskRunContext,
    TaskSpec,
)


class RecordingRunner:
    def __init__(self, results: dict[str, AgentResultV1] | None = None, delay: float = 0.0) -> None:
        self.results = results or {}
        self.delay = delay
        self.calls: list[tuple[str, list[str]]] = []

    async def run(self, task: TaskSpec, context: TaskRunContext) -> AgentResultV1:
        self.calls.append((task.id, sorted(context.dependency_results)))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.results.get(task.id, AgentResultV1(status="passed", summary=f"done:{task.id}"))


def test_cycle_rejected_before_run() -> None:
    scheduler = StaticDagScheduler(RecordingRunner())

    with pytest.raises(StaticDagError):
        asyncio.run(
            scheduler.run(
                [
                    TaskSpec(id="a", input="a", depends_on=["b"]),
                    TaskSpec(id="b", input="b", depends_on=["a"]),
                ]
            )
        )


@pytest.mark.asyncio
async def test_three_stage_order_and_isolation() -> None:
    runner = RecordingRunner()
    scheduler = StaticDagScheduler(runner)

    results = await scheduler.run(
        [
            TaskSpec(id="source_a", input="a"),
            TaskSpec(id="source_b", input="b"),
            TaskSpec(id="middle", input="m", depends_on=["source_a"]),
            TaskSpec(id="final", input="f", depends_on=["middle", "source_b"]),
        ]
    )

    assert results["final"].status == "passed"
    assert runner.calls[:2] == [("source_a", []), ("source_b", [])]
    assert ("middle", ["source_a"]) in runner.calls
    assert ("final", ["middle", "source_b"]) in runner.calls
    assert ("middle", ["source_a", "source_b"]) not in runner.calls


@pytest.mark.asyncio
async def test_upstream_failure_blocks_dependents() -> None:
    runner = RecordingRunner(
        {"bad": AgentResultV1(status="failed", summary="bad failed")}
    )
    scheduler = StaticDagScheduler(runner)

    results = await scheduler.run(
        [
            TaskSpec(id="bad", input="bad"),
            TaskSpec(id="independent", input="ok"),
            TaskSpec(id="downstream", input="blocked", depends_on=["bad"]),
        ]
    )

    assert results["bad"].status == "failed"
    assert results["independent"].status == "passed"
    assert results["downstream"].status == "failed"
    assert results["downstream"].extra == {"blocked": True, "blocked_by": ["bad"]}
    assert "downstream" not in [task_id for task_id, _ in runner.calls]


@pytest.mark.asyncio
async def test_timeout_treated_as_failure() -> None:
    runner = RecordingRunner(delay=0.05)
    scheduler = StaticDagScheduler(runner)

    results = await scheduler.run([TaskSpec(id="slow", input="slow", timeout_seconds=0.01)])

    assert results["slow"].status == "failed"
    assert "超时" in results["slow"].summary
