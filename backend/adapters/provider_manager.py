from __future__ import annotations

from typing import Any

from backend.common import LLMError
from backend.common.types import ProviderConfig

from .base import LLMAdapter
from .factory import AdapterFactory


class ProviderManager:
    """管理所有 Provider 配置，对应 Web UI 设置页面的 CRUD"""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderConfig] = {}
        self._adapters: dict[str, LLMAdapter] = {}

    async def add(self, config: ProviderConfig) -> ProviderConfig:
        try:
            if config.id in self._providers:
                raise LLMError("PROVIDER_EXISTS", f"Provider already exists: {config.id}", "provider_manager")
            self._providers[config.id] = config
            if config.is_default or not any(item.is_default for item in self._providers.values()):
                await self.set_default(config.id)
            return self._providers[config.id]
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_ADD_ERROR", str(exc), "provider_manager") from exc

    async def update(self, provider_id: str, **kwargs: Any) -> ProviderConfig:
        try:
            if provider_id not in self._providers:
                raise LLMError("PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}", "provider_manager")
            kwargs.pop("id", None)
            updated = self._providers[provider_id].model_copy(update=kwargs)
            self._providers[provider_id] = updated
            self._adapters.pop(provider_id, None)
            if updated.is_default:
                await self.set_default(provider_id)
            return self._providers[provider_id]
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_UPDATE_ERROR", str(exc), "provider_manager") from exc

    async def remove(self, provider_id: str) -> bool:
        try:
            removed = self._providers.pop(provider_id, None)
            self._adapters.pop(provider_id, None)
            if removed is None:
                return False
            if removed.is_default and self._providers:
                first_id = next(iter(self._providers))
                await self.set_default(first_id)
            return True
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_REMOVE_ERROR", str(exc), "provider_manager") from exc

    async def list_all(self) -> list[ProviderConfig]:
        try:
            return list(self._providers.values())
        except Exception as exc:
            raise LLMError("PROVIDER_LIST_ERROR", str(exc), "provider_manager") from exc

    async def get_default(self) -> ProviderConfig | None:
        try:
            for config in self._providers.values():
                if config.is_default:
                    return config
            return None
        except Exception as exc:
            raise LLMError("PROVIDER_DEFAULT_ERROR", str(exc), "provider_manager") from exc

    async def set_default(self, provider_id: str) -> None:
        try:
            if provider_id not in self._providers:
                raise LLMError("PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}", "provider_manager")
            for item_id, config in list(self._providers.items()):
                is_default = item_id == provider_id
                if config.is_default != is_default:
                    self._providers[item_id] = config.model_copy(update={"is_default": is_default})
                    self._adapters.pop(item_id, None)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_SET_DEFAULT_ERROR", str(exc), "provider_manager") from exc

    async def test_connection(self, provider_id: str) -> bool:
        try:
            adapter = await self.get_adapter(provider_id)
            return await adapter.test_connection()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_TEST_ERROR", str(exc), "provider_manager") from exc

    async def get_adapter(self, provider_id: str | None = None) -> LLMAdapter:
        try:
            target_id = provider_id
            if target_id is None:
                default = await self.get_default()
                if default is None:
                    raise LLMError("DEFAULT_PROVIDER_MISSING", "Default provider is not configured", "provider_manager")
                target_id = default.id
            config = self._providers.get(target_id)
            if config is None:
                raise LLMError("PROVIDER_NOT_FOUND", f"Provider not found: {target_id}", "provider_manager")
            if target_id not in self._adapters:
                self._adapters[target_id] = AdapterFactory.create(config)
            return self._adapters[target_id]
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_ADAPTER_ERROR", str(exc), "provider_manager") from exc


__all__ = ["ProviderManager"]
