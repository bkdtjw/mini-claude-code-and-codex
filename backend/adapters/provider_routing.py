from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.common.logging import get_logger
from backend.common.types import ProviderConfig
from backend.config.settings import settings as app_settings

from .base import LLMAdapter
from .resilient_adapter import LLMCandidate, ResilientAdapterConfig, ResilientLLMAdapter

logger = get_logger(component="provider_routing")


@dataclass(frozen=True)
class ProviderRoutingContext:
    primary: ProviderConfig
    providers: dict[str, ProviderConfig]
    base_adapter: Callable[[ProviderConfig], LLMAdapter]
    routed_adapters: dict[str, LLMAdapter]


def get_resilient_adapter(context: ProviderRoutingContext) -> LLMAdapter | None:
    fallback_ids = _fallback_provider_ids(context.primary.id, context.providers)
    if not fallback_ids:
        return None
    route_key = f"{context.primary.id}:{','.join(fallback_ids)}"
    if route_key in context.routed_adapters:
        return context.routed_adapters[route_key]
    fallback_configs = [context.providers[item] for item in fallback_ids if item in context.providers]
    if not fallback_configs:
        return None
    fallbacks = [
        LLMCandidate(item.id, item.default_model, context.base_adapter(item))
        for item in fallback_configs
        if item.enabled
    ]
    if not fallbacks:
        return None
    adapter = ResilientLLMAdapter(
        primary=LLMCandidate(
            context.primary.id,
            context.primary.default_model,
            context.base_adapter(context.primary),
        ),
        fallbacks=fallbacks,
        config=ResilientAdapterConfig(
            fallback_error_codes=_csv_set(app_settings.llm_fallback_error_codes),
            deadline_seconds=app_settings.llm_fallback_deadline_seconds,
            circuit_threshold=app_settings.llm_fallback_circuit_threshold,
            circuit_seconds=app_settings.llm_fallback_circuit_seconds,
        ),
    )
    context.routed_adapters[route_key] = adapter
    logger.info(
        "provider_router_created",
        provider_id=context.primary.id,
        fallback_ids=fallback_ids,
    )
    return adapter


def _fallback_provider_ids(primary_id: str, providers: dict[str, ProviderConfig]) -> list[str]:
    return [
        item
        for item in _csv_list(app_settings.llm_fallback_provider_ids)
        if item != primary_id and item in providers
    ]


def _csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _csv_set(value: str) -> frozenset[str]:
    return frozenset(_csv_list(value))


__all__ = ["ProviderRoutingContext", "get_resilient_adapter"]
