from __future__ import annotations

from backend.common.logging import get_logger

from .models import AgentCategory, AgentSpec

logger = get_logger(component="spec_registry")


class SpecRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        if spec.id in self._specs:
            logger.warning("spec_overridden", spec_id=spec.id)
        self._specs[spec.id] = spec

    def get(self, spec_id: str) -> AgentSpec | None:
        return self._specs.get(spec_id)

    def list_all(self) -> list[AgentSpec]:
        return [spec for spec in self._sorted_specs() if spec.enabled]

    def list_by_category(self, category: AgentCategory) -> list[AgentSpec]:
        return [spec for spec in self.list_all() if spec.category == category]

    def search(self, keyword: str) -> list[AgentSpec]:
        normalized = keyword.strip().lower()
        if not normalized:
            return self.list_all()
        return [
            spec
            for spec in self.list_all()
            if normalized in spec.title.lower() or normalized in spec.description.lower()
        ]

    def summary(self) -> list[dict[str, str]]:
        return [
            {
                "id": spec.id,
                "title": spec.title,
                "category": spec.category.value,
                "description": self._preview(spec.description),
            }
            for spec in self.list_all()
        ]

    def _sorted_specs(self) -> list[AgentSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    @staticmethod
    def _preview(text: str) -> str:
        normalized = " ".join(text.split())
        return normalized[:100]


__all__ = ["SpecRegistry"]
