from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.adapters.resilient_adapter import (
    LLMCandidate,
    ResilientAdapterConfig,
    ResilientLLMAdapter,
)
from backend.common import LLMError
from backend.common.types import LLMRequest, LLMResponse, Message, StreamChunk


class FakeAdapter(LLMAdapter):
    def __init__(self, outcomes: list[LLMResponse | LLMError], delay: float = 0.0) -> None:
        self.outcomes = outcomes
        self.delay = delay
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, LLMError):
            raise outcome
        return outcome

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        _ = request
        yield StreamChunk(type="done")


def _request() -> LLMRequest:
    return LLMRequest(model="glm-5.1", messages=[Message(role="user", content="hello")])


def _config(**kwargs: object) -> ResilientAdapterConfig:
    return ResilientAdapterConfig(
        fallback_error_codes=frozenset(
            {
                "NETWORK_ERROR",
                "RATE_LIMIT",
                "RATE_LIMIT_1113",
                "RATE_LIMIT_1305",
                "RATE_LIMIT_1312",
                "SERVER_ERROR",
            }
        ),
        **kwargs,
    )


def _router(
    primary_adapter: FakeAdapter,
    fallback_adapter: FakeAdapter,
    config: ResilientAdapterConfig | None = None,
) -> ResilientLLMAdapter:
    return ResilientLLMAdapter(
        primary=LLMCandidate("zhipu", "glm-5.1", primary_adapter),
        fallbacks=[LLMCandidate("kimi", "kimi-k2.6", fallback_adapter)],
        config=config or _config(),
    )


@pytest.mark.asyncio
async def test_fallback_on_network_error_switches_provider_and_model() -> None:
    primary = FakeAdapter([LLMError("NETWORK_ERROR", "timeout", "zhipu")])
    fallback = FakeAdapter([LLMResponse(content="ok")])

    response = await _router(primary, fallback).complete(_request())

    assert response.content == "ok"
    assert fallback.requests[0].model == "kimi-k2.6"
    assert response.provider_metadata["selected_provider"] == "kimi"
    assert response.provider_metadata["fallback_from_provider"] == "zhipu"


@pytest.mark.asyncio
async def test_fallback_on_provider_capacity_rate_limit_code() -> None:
    primary = FakeAdapter([LLMError("RATE_LIMIT_1113", "capacity exceeded", "zhipu", 429)])
    fallback = FakeAdapter([LLMResponse(content="ok")])

    response = await _router(primary, fallback).complete(_request())

    assert response.content == "ok"
    assert fallback.requests[0].model == "kimi-k2.6"
    assert response.provider_metadata["selected_provider"] == "kimi"
    assert response.provider_metadata["fallback_from_provider"] == "zhipu"


@pytest.mark.asyncio
async def test_does_not_fallback_on_account_rate_limit_code() -> None:
    primary = FakeAdapter(
        [
            LLMError("RATE_LIMIT_1302", "too many requests", "zhipu", 429),
            LLMError("RATE_LIMIT_1302", "too many requests", "zhipu", 429),
        ]
    )
    fallback = FakeAdapter([LLMResponse(content="should not run")])
    router = _router(primary, fallback, _config(circuit_threshold=1))

    with pytest.raises(LLMError) as exc_info:
        await router.complete(_request())
    with pytest.raises(LLMError):
        await router.complete(_request())

    assert exc_info.value.code == "RATE_LIMIT_1302"
    assert fallback.requests == []
    assert len(primary.requests) == 2


@pytest.mark.asyncio
async def test_circuit_skips_primary_after_threshold() -> None:
    primary = FakeAdapter(
        [
            LLMError("NETWORK_ERROR", "timeout", "zhipu"),
            LLMError("NETWORK_ERROR", "timeout", "zhipu"),
        ]
    )
    fallback = FakeAdapter([LLMResponse(content="one"), LLMResponse(content="two"), LLMResponse(content="three")])
    router = _router(primary, fallback, _config(circuit_threshold=2, circuit_seconds=300.0))

    await router.complete(_request())
    await router.complete(_request())
    response = await router.complete(_request())

    assert response.content == "three"
    assert len(primary.requests) == 2
    assert len(fallback.requests) == 3


@pytest.mark.asyncio
async def test_deadline_bounds_slow_provider_call() -> None:
    primary = FakeAdapter([LLMResponse(content="late")], delay=0.05)
    fallback = FakeAdapter([LLMResponse(content="unused")])
    router = _router(primary, fallback, _config(deadline_seconds=0.01))

    with pytest.raises(LLMError) as exc_info:
        await router.complete(_request())

    assert exc_info.value.code == "ALL_PROVIDERS_FAILED"
    assert len(fallback.requests) == 0
