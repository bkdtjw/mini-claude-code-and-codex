from __future__ import annotations


class ThresholdPolicy:
    def __init__(
        self,
        max_context_tokens: int = 180000,
        compact_threshold_ratio: float = 0.90,
        reserve_recent_count: int = 6,
    ) -> None:
        self._max_context_tokens = max_context_tokens
        self._compact_threshold_ratio = compact_threshold_ratio
        self._reserve_recent_count = reserve_recent_count

    def should_compact(self, current_tokens: int) -> bool:
        threshold = int(self._max_context_tokens * self._compact_threshold_ratio)
        return current_tokens >= threshold

    def get_reserve_count(self) -> int:
        return self._reserve_recent_count


__all__ = ["ThresholdPolicy"]
