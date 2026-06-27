from __future__ import annotations

from .config import PipelineConfig
from .models import TweetCandidate


def curate_candidates(
    candidates: list[TweetCandidate],
    config: PipelineConfig,
) -> list[TweetCandidate]:
    """High-quality curation: hard-drop spam / already-reported / stale / low-score.

    Only active when ``config.curated`` is True. Inclusive mode keeps every
    candidate and relies on the soft penalties applied during scoring.
    """
    if not config.curated:
        return candidates
    return [candidate for candidate in candidates if _keep(candidate, config)]


def _keep(candidate: TweetCandidate, config: PipelineConfig) -> bool:
    if "spam" in candidate.penalties:
        return False
    if candidate.hours_ago > config.max_age_hours:
        return False
    if candidate.score_parts.get("novelty", 100.0) < 100.0:
        return False
    return candidate.score >= config.min_keep_score


__all__ = ["curate_candidates"]
