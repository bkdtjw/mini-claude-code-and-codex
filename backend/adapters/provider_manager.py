from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.common import LLMError
from backend.common.types import ProviderConfig

from .base import LLMAdapter
from .factory import AdapterFactory


class ProviderManager:
    """Manage provider configs with JSON persistence."""

    def __init__(self) -> None:
        self._config_path = Path(__file__).resolve().parents[1] / "config" / "providers.json"
        self._aliases = {
            "openai": "openai_compat",
            "openai_compatible": "openai_compat",
            "claude_compat": "anthropic",
            "anthropic_compat": "anthropic",
        }
        self._providers: dict[str, ProviderConfig] = {}
        self._adapters: dict[str, LLMAdapter] = {}
        self._last_mtime: float | None = None
        self._load_from_file(force=True)

    def _normalize_provider_type(self, value: Any) -> Any:
        return self._aliases.get(value, value) if isinstance(value, str) else value

    def _normalize_defaults(self, data: dict[str, ProviderConfig]) -> dict[str, ProviderConfig]:
        if data and not any(item.is_default for item in data.values()):
            first_id = next(iter(data))
            data[first_id] = data[first_id].model_copy(update={"is_default": True})
        return data

    def _load_from_file(self, force: bool = False) -> None:
        if not self._config_path.exists():
            self._providers, self._last_mtime = {}, None
            return
        mtime = self._config_path.stat().st_mtime
        if not force and self._last_mtime is not None and mtime <= self._last_mtime:
            return
        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
            rows = raw.get("providers", []) if isinstance(raw, dict) else []
            loaded: dict[str, ProviderConfig] = {}
            for row in rows:
                item = dict(row)
                item["provider_type"] = self._normalize_provider_type(item.get("provider_type"))
                config = ProviderConfig.model_validate(item)
                loaded[config.id] = config
            self._providers = self._normalize_defaults(loaded)
            self._adapters.clear()
            self._last_mtime = mtime
        except Exception:
            self._providers, self._adapters = {}, {}

    def _save_to_file(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"providers": [item.model_dump(mode="json") for item in self._providers.values()]}
        self._config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._last_mtime = self._config_path.stat().st_mtime

    async def add(self, config: ProviderConfig) -> ProviderConfig:
        try:
            self._load_from_file()
            if config.id in self._providers:
                raise LLMError("PROVIDER_EXISTS", f"Provider already exists: {config.id}", "provider_manager")
            self._providers[config.id] = config
            if config.is_default or not any(item.is_default for item in self._providers.values()):
                await self.set_default(config.id)
            else:
                self._save_to_file()
            return self._providers[config.id]
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_ADD_ERROR", str(exc), "provider_manager") from exc

    async def update(self, provider_id: str, **kwargs: Any) -> ProviderConfig:
        try:
            self._load_from_file()
            if provider_id not in self._providers:
                raise LLMError("PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}", "provider_manager")
            kwargs.pop("id", None)
            if "provider_type" in kwargs:
                kwargs["provider_type"] = self._normalize_provider_type(kwargs["provider_type"])
            updated = self._providers[provider_id].model_copy(update=kwargs)
            self._providers[provider_id] = updated
            self._adapters.pop(provider_id, None)
            if updated.is_default:
                await self.set_default(provider_id)
            else:
                self._save_to_file()
            return self._providers[provider_id]
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_UPDATE_ERROR", str(exc), "provider_manager") from exc

    async def remove(self, provider_id: str) -> bool:
        try:
            self._load_from_file()
            removed = self._providers.pop(provider_id, None)
            self._adapters.pop(provider_id, None)
            if removed is None:
                return False
            if removed.is_default and self._providers:
                await self.set_default(next(iter(self._providers)))
            else:
                self._save_to_file()
            return True
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_REMOVE_ERROR", str(exc), "provider_manager") from exc

    async def list_all(self) -> list[ProviderConfig]:
        try:
            self._load_from_file()
            return list(self._providers.values())
        except Exception as exc:
            raise LLMError("PROVIDER_LIST_ERROR", str(exc), "provider_manager") from exc

    async def get_default(self) -> ProviderConfig | None:
        try:
            self._load_from_file()
            return next((item for item in self._providers.values() if item.is_default), None)
        except Exception as exc:
            raise LLMError("PROVIDER_DEFAULT_ERROR", str(exc), "provider_manager") from exc

    async def set_default(self, provider_id: str) -> None:
        try:
            self._load_from_file()
            if provider_id not in self._providers:
                raise LLMError("PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}", "provider_manager")
            for item_id, config in list(self._providers.items()):
                is_default = item_id == provider_id
                if config.is_default != is_default:
                    self._providers[item_id] = config.model_copy(update={"is_default": is_default})
                    self._adapters.pop(item_id, None)
            self._save_to_file()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_SET_DEFAULT_ERROR", str(exc), "provider_manager") from exc

    async def test_connection(self, provider_id: str) -> bool:
        try:
            self._load_from_file()
            return await (await self.get_adapter(provider_id)).test_connection()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("PROVIDER_TEST_ERROR", str(exc), "provider_manager") from exc

    async def get_adapter(self, provider_id: str | None = None) -> LLMAdapter:
        try:
            self._load_from_file()
            target_id = provider_id
            if target_id is None:
                default = await self.get_default()
                target_id = default.id if default else None
            if target_id is None:
                raise LLMError("DEFAULT_PROVIDER_MISSING", "Default provider is not configured", "provider_manager")
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
