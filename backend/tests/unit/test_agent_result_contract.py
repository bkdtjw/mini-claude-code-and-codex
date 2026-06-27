from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.metrics import close_metrics, get_metrics, init_metrics
from backend.common.types import LLMRequest, LLMResponse, StreamChunk
from backend.core.s04_sub_agents import MAX_REPAIR_INPUT_CHARS, coerce_agent_result, parse_agent_result

from .redis_test_support import use_fake_redis


class RepairAdapter(LLMAdapter):
    def __init__(self, responses: list[str], fail: bool = False) -> None:
        self.responses = responses
        self.fail = fail
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("repair unavailable")
        if not self.responses:
            return LLMResponse(content="not json")
        return LLMResponse(content=self.responses.pop(0))

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        _ = request
        if False:
            yield StreamChunk(type="done")


def _valid_json(summary: str = "ok") -> str:
    return (
        '{"status":"passed","summary":"'
        + summary
        + '","findings":[],"artifacts":[],"next_steps":[],"extra":{}}'
    )


def test_valid_result_passes() -> None:
    result = parse_agent_result(_valid_json("validated"))

    assert result.status == "passed"
    assert result.summary == "validated"


@pytest.mark.asyncio
async def test_malformed_triggers_repair() -> None:
    adapter = RepairAdapter([_valid_json("repaired")])

    result = await coerce_agent_result(
        '```json\n{"status":"passed"}\n```',
        adapter=adapter,
        model="kimi-k2.6",
    )

    assert result.status == "passed"
    assert result.summary == "repaired"
    assert len(adapter.requests) == 1
    assert "只返回 JSON object" in adapter.requests[0].system_prompt


@pytest.mark.asyncio
async def test_unrepairable_falls_back() -> None:
    adapter = RepairAdapter(["still bad", "also bad"])

    result = await coerce_agent_result("plain text", adapter=adapter, model="kimi-k2.6")

    assert result.status == "unparsed"
    assert result.raw_output == "plain text"
    assert result.findings[0].title == "子 agent 输出格式错误"
    assert len(adapter.requests) == 2


@pytest.mark.asyncio
async def test_pipeline_never_throws_on_bad_output() -> None:
    adapter = RepairAdapter([], fail=True)

    result = await coerce_agent_result("{{{{", adapter=adapter, model="kimi-k2.6")

    assert result.status == "unparsed"
    assert result.raw_output == "{{{{"

@pytest.mark.asyncio
async def test_large_bad_output_skips_repair_call() -> None:
    adapter = RepairAdapter([_valid_json("should not call")])
    raw = "x" * (MAX_REPAIR_INPUT_CHARS + 1)

    result = await coerce_agent_result(raw, adapter=adapter, model="kimi-k2.6")

    assert result.status == "unparsed"
    assert result.raw_output == raw
    assert adapter.requests == []


@pytest.mark.asyncio
async def test_repair_timeout_falls_back() -> None:
    class SlowRepairAdapter(RepairAdapter):
        async def complete(self, request: LLMRequest) -> LLMResponse:
            self.requests.append(request)
            await asyncio.sleep(0.05)
            return LLMResponse(content=_valid_json("late"))

    adapter = SlowRepairAdapter([])

    result = await coerce_agent_result(
        "plain text",
        adapter=adapter,
        model="kimi-k2.6",
        max_repair_attempts=1,
        repair_timeout_seconds=0.01,
    )

    assert result.status == "unparsed"
    assert len(adapter.requests) == 1


@pytest.mark.asyncio
async def test_coerce_agent_result_records_parse_repair_and_fallback_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await use_fake_redis(monkeypatch)
    close_metrics()
    await init_metrics()

    await coerce_agent_result(_valid_json("parsed"))
    await coerce_agent_result("bad", adapter=RepairAdapter([_valid_json("repaired")]), model="m")
    await coerce_agent_result("bad")
    collector = await get_metrics()

    assert await collector.get("sub_agent_result_parsed") == 1
    assert await collector.get("sub_agent_result_repaired") == 1
    assert await collector.get("sub_agent_result_fallbacks") == 1
