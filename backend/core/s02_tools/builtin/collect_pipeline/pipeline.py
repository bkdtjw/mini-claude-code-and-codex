from __future__ import annotations

from .config import PipelineConfig
from .models import (
    CollectAndProcessPipelineError,
    PipelineResult,
    RawTweet,
    RawVideo,
    TaskMemory,
)
from .rendering import render_evidence
from .scoring import build_clusters, build_tweet_candidates


async def process_raw_data(
    tweets: dict[str, list[RawTweet]],
    videos: list[RawVideo],
    config: PipelineConfig,
    memory: TaskMemory | None,
) -> PipelineResult:
    try:
        tweet_counts = {keyword: len(items) for keyword, items in tweets.items()}
        candidates = build_tweet_candidates(tweets, config, memory)
        clusters = build_clusters(candidates, config)
        evidence_text, reported_ids, reported_signatures, evidence_cards = render_evidence(
            tweet_counts,
            clusters,
            videos,
            config,
        )
        return PipelineResult(
            evidence_text=evidence_text,
            stats={
                "tweet_counts_by_keyword": tweet_counts,
                "tweet_candidates": len(candidates),
                "tweet_clusters": len(clusters),
                "video_count": len(videos),
                "evidence_cards": evidence_cards,
                "reported_ids": reported_ids,
                "reported_signatures": reported_signatures,
            },
        )
    except CollectAndProcessPipelineError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CollectAndProcessPipelineError(f"Raw data processing failed: {exc}") from exc

__all__ = ["process_raw_data"]
