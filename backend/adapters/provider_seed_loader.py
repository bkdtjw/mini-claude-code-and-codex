from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.common.types import ProviderConfig

DEFAULT_PROVIDER_SEED_PATH = Path(__file__).resolve().parents[1] / "config" / "providers.json"


def load_provider_seed(seed_path: Path, aliases: dict[str, str]) -> list[ProviderConfig]:
    try:
        if not seed_path.exists():
            return []
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
        rows = raw.get("providers", []) if isinstance(raw, dict) else []
        return [ProviderConfig.model_validate(_normalize_provider_row(row, aliases)) for row in rows]
    except Exception:
        return []


def _normalize_provider_row(row: Any, aliases: dict[str, str]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    provider_type = row.get("provider_type")
    if isinstance(provider_type, str):
        provider_type = aliases.get(provider_type, provider_type)
    return {**row, "provider_type": provider_type}


__all__ = ["DEFAULT_PROVIDER_SEED_PATH", "load_provider_seed"]
