from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from backend.common import LLMError
from backend.common.logging import get_logger
from backend.common.types import LLMRequest, LLMResponse, StreamChunk

from .base import LLMAdapter

logger = get_logger(component="resilient_adapter")


@dataclass(frozen=True)
class LLMCandidate:
    provider_id: str
    model: str
    adapter: LLMAdapter


@dataclass(frozen=True)
class ResilientAdapterConfig:
    fallback_error_codes: frozenset[str]
    deadline_seconds: float = 180.0
    circuit_threshold: int = 3
    circuit_seconds: float = 300.0


@dataclass
class CircuitEntry:
    failures: int = 0
    opened_until: float = 0.0


class CircuitBreaker:
    def __init__(self, threshold: int, open_seconds: float) -> None:
        self._threshold = threshold
        self._open_seconds = open_seconds
        self._entries: dict[str, CircuitEntry] = {}

    def is_open(self, provider_id: str) -> bool:
        entry = self._entries.get(provider_id)
        return bool(entry and entry.opened_until > monotonic())

    def record_success(self, provider_id: str) -> None:
        self._entries.pop(provider_id, None)

    def record_failure(self, provider_id: str) -> None:
        entry = self._entries.setdefault(provider_id, CircuitEntry())
        entry.failures += 1
        if entry.failures >= self._threshold:
            entry.opened_until = monotonic() + self._open_seconds
            logger.warning("llm_circuit_opened", provider_id=provider_id)


class ResilientLLMAdapter(LLMAdapter):
    def __init__(
        self,
        primary: LLMCandidate,
        fallbacks: list[LLMCandidate],
        config: ResilientAdapterConfig,
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks
        self._config = config
        self._breaker = CircuitBreaker(config.circuit_threshold, config.circuit_seconds)

    async def test_connection(self) -> bool:
        try:
            return await self._primary.adapter.test_connection()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("RESILIENT_TEST_ERROR", str(exc), "router") from exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            started = monotonic()
            errors: list[LLMError] = []
            for candidate in self._candidates():
                if self._breaker.is_open(candidate.provider_id):
                    logger.warning("llm_candidate_skipped_circuit", provider_id=candidate.provider_id)
                    continue
                remaining = self._remaining(started)
                if remaining <= 0:
                    break
                try:
                    async with asyncio.timeout(remaining):
                        response = await candidate.adapter.complete(
                            self._request_for_candidate(request, candidate)
                        )
                    self._breaker.record_success(candidate.provider_id)
                    logger.info(
                        "llm_candidate_succeeded",
                        provider_id=candidate.provider_id,
                        model=candidate.model,
                        fallback_from_provider=(
                            self._primary.provider_id
                            if candidate.provider_id != self._primary.provider_id
                            else ""
                        ),
                    )
                    return self._annotate_response(response, candidate)
                except TimeoutError:
                    error = LLMError(
                        "NETWORK_ERROR",
                        f"LLM call exceeded fallback deadline ({int(remaining)}s)",
                        candidate.provider_id,
                        None,
                    )
                    self._breaker.record_failure(candidate.provider_id)
                    errors.append(error)
                    logger.warning("llm_candidate_timeout", provider_id=candidate.provider_id)
                    continue
                except LLMError as exc:
                    errors.append(exc)
                    can_fallback = self._can_fallback(exc)
                    if can_fallback:
                        self._breaker.record_failure(candidate.provider_id)
                    if not can_fallback:
                        raise
                    logger.warning(
                        "llm_candidate_failed_fallback",
                        provider_id=candidate.provider_id,
                        error_code=exc.code,
                    )
                    continue
            raise self._failed_error(errors)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("RESILIENT_COMPLETE_ERROR", str(exc), "router") from exc

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            errors: list[LLMError] = []
            for candidate in self._candidates():
                if self._breaker.is_open(candidate.provider_id):
                    continue
                emitted = False
                try:
                    async for chunk in candidate.adapter.stream(
                        self._request_for_candidate(request, candidate)
                    ):
                        emitted = True
                        yield chunk
                    self._breaker.record_success(candidate.provider_id)
                    return
                except LLMError as exc:
                    errors.append(exc)
                    can_fallback = self._can_fallback(exc)
                    if can_fallback:
                        self._breaker.record_failure(candidate.provider_id)
                    if emitted or not can_fallback:
                        raise
                    continue
            raise self._failed_error(errors)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("RESILIENT_STREAM_ERROR", str(exc), "router") from exc

    def _candidates(self) -> list[LLMCandidate]:
        return [self._primary, *self._fallbacks]

    def _remaining(self, started: float) -> float:
        return self._config.deadline_seconds - (monotonic() - started)

    def _request_for_candidate(
        self,
        request: LLMRequest,
        candidate: LLMCandidate,
    ) -> LLMRequest:
        if candidate.provider_id == self._primary.provider_id:
            return request.model_copy(update={"model": request.model or candidate.model})
        return request.model_copy(update={"model": candidate.model})

    def _can_fallback(self, exc: LLMError) -> bool:
        return exc.code in self._config.fallback_error_codes

    def _annotate_response(
        self,
        response: LLMResponse,
        candidate: LLMCandidate,
    ) -> LLMResponse:
        metadata = {
            **response.provider_metadata,
            "selected_provider": candidate.provider_id,
            "selected_model": candidate.model,
        }
        if candidate.provider_id != self._primary.provider_id:
            metadata["fallback_from_provider"] = self._primary.provider_id
        return response.model_copy(update={"provider_metadata": metadata})

    def _failed_error(self, errors: list[LLMError]) -> LLMError:
        if not errors:
            return LLMError("ALL_PROVIDERS_FAILED", "No LLM provider available", "router")
        detail = "; ".join(f"{err.provider}:{err.code}" for err in errors)
        return LLMError("ALL_PROVIDERS_FAILED", detail, "router")


__all__ = ["LLMCandidate", "ResilientAdapterConfig", "ResilientLLMAdapter"]
