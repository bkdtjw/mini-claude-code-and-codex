from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.common import LLMError
from backend.common.types import ProviderConfig

from .base import LLMAdapter
from .factory import AdapterFactory
from .provider_seed_loader import load_provider_seed


def normalize_provider_type(value: Any, aliases: dict[str, str]) -> Any:
    return aliases.get(value, value) if isinstance(value, str) else value


def normalize_defaults(data: dict[str, ProviderConfig]) -> dict[str, ProviderConfig]:
    if data and not any(item.is_default for item in data.values()):
        first_id = next(iter(data))
        data[first_id] = data[first_id].model_copy(update={"is_default": True})
    return data


def load_json_seed(path: Path, aliases: dict[str, str]) -> list[ProviderConfig]:
    return load_provider_seed(path, aliases)


def get_base_adapter(
    config: ProviderConfig,
    adapters: dict[str, LLMAdapter],
) -> LLMAdapter:
    if config.id not in adapters:
        adapters[config.id] = AdapterFactory.create(config)
    return adapters[config.id]


async def set_default_locked(
    provider_id: str,
    store: Any,
    providers: dict[str, ProviderConfig],
    adapters: dict[str, LLMAdapter],
    routed_adapters: dict[str, LLMAdapter],
) -> None:
    if provider_id not in providers:
        raise LLMError("PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}", "provider_manager")
    await store.set_default(provider_id)
    for item_id, config in list(providers.items()):
        is_default = item_id == provider_id
        if config.is_default != is_default:
            providers[item_id] = config.model_copy(update={"is_default": is_default})
            adapters.pop(item_id, None)
            routed_adapters.clear()


__all__ = [
    "get_base_adapter",
    "load_json_seed",
    "normalize_defaults",
    "normalize_provider_type",
    "set_default_locked",
]
