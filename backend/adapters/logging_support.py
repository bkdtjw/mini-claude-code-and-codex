from __future__ import annotations

from time import monotonic
from typing import Any

from backend.common import LLMError
from backend.common.logging import get_logger
from backend.common.metrics import incr
from backend.common.types import LLMResponse


def adapter_logger(component: str) -> Any:
    return get_logger(component=component)


def log_llm_request_start(
    logger: Any,
    *,
    model: str,
    provider: str,
    request_type: str,
) -> float:
    started_at = monotonic()
    logger.info(
        "llm_request_start",
        model=model,
        provider=provider,
        request_type=request_type,
    )
    return started_at


def log_llm_request_end(
    logger: Any,
    *,
    model: str,
    provider: str,
    request_type: str,
    started_at: float,
    response: LLMResponse | None = None,
) -> None:
    payload: dict[str, Any] = {
        "model": model,
        "provider": provider,
        "request_type": request_type,
        "duration_ms": int((monotonic() - started_at) * 1000),
    }
    if response is not None:
        payload["prompt_tokens"] = response.usage.prompt_tokens
        payload["completion_tokens"] = response.usage.completion_tokens
        payload["cached_prompt_tokens"] = response.usage.cached_prompt_tokens
    logger.info("llm_request_end", **payload)


def log_llm_request_retry(
    logger: Any,
    *,
    attempt: int,
    provider: str,
    request_type: str,
    reason: str,
    status_code: int | None = None,
) -> None:
    logger.warning(
        "llm_request_retry",
        provider=provider,
        request_type=request_type,
        attempt=attempt,
        status_code=status_code,
        reason=reason,
    )


def log_llm_request_error(
    logger: Any,
    *,
    model: str,
    provider: str,
    request_type: str,
    exc: Exception,
) -> None:
    logger.error(
        "llm_request_error",
        model=model,
        provider=provider,
        request_type=request_type,
        error_code=exc.code if isinstance(exc, LLMError) else type(exc).__name__,
        error_message=str(exc),
    )


async def incr_llm_success(response: LLMResponse | None = None) -> None:
    await incr("llm_calls")
    if response is None:
        return
    await incr("llm_prompt_tokens", response.usage.prompt_tokens)
    await incr("llm_completion_tokens", response.usage.completion_tokens)
    if response.usage.cached_prompt_tokens:
        await incr("llm_cached_prompt_tokens", response.usage.cached_prompt_tokens)


async def incr_llm_error() -> None:
    await incr("llm_errors")


__all__ = [
    "adapter_logger",
    "incr_llm_error",
    "incr_llm_success",
    "log_llm_request_end",
    "log_llm_request_error",
    "log_llm_request_retry",
    "log_llm_request_start",
]
