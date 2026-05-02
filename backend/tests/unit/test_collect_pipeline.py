from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.core.s02_tools.builtin.collect_and_process_support import (
    PipelineConfig,
    RawTweet,
    process_raw_data,
)


@pytest.mark.asyncio
async def test_pipeline_keeps_short_spammy_tweet_with_soft_penalty() -> None:
    tweet = _tweet("promo code", url="https://x.com/ad/status/1", retweets=20)

    result = await process_raw_data({"LLM": [tweet]}, [], PipelineConfig(), None)

    assert "promo code" in result.evidence_text
    assert result.stats["evidence_cards"] == 1


@pytest.mark.asyncio
async def test_pipeline_exact_merge_combines_keyword_hits() -> None:
    url = "https://x.com/openai/status/2"
    tweet = _tweet("OpenAI GPT-5 launch details", url=url)

    result = await process_raw_data({"OpenAI": [tweet], "GPT-5": [tweet]}, [], PipelineConfig(), None)

    assert result.stats["tweet_candidates"] == 1
    assert "关键词: OpenAI, GPT-5" in result.evidence_text


@pytest.mark.asyncio
async def test_pipeline_clusters_same_event_without_deleting_urls() -> None:
    tweets = [
        _tweet("OpenAI GPT-5 launch focuses on reasoning", url="https://x.com/a/status/3"),
        _tweet("GPT-5 from OpenAI improves coding and reasoning", url="https://x.com/b/status/4"),
    ]

    result = await process_raw_data({"OpenAI": tweets}, [], PipelineConfig(), None)

    assert result.stats["tweet_clusters"] == 1
    assert "另见:" in result.evidence_text
    assert "https://x.com/a/status/3" in result.evidence_text
    assert "https://x.com/b/status/4" in result.evidence_text
    assert len(result.stats["reported_ids"]) == 2
    assert result.stats["reported_signatures"]


@pytest.mark.asyncio
async def test_pipeline_does_not_cluster_outside_time_window() -> None:
    now = datetime.now(UTC)
    tweets = [
        _tweet("OpenAI GPT-5 launch focuses on reasoning", "https://x.com/a/status/5", created_at=now),
        _tweet(
            "GPT-5 from OpenAI improves coding and reasoning",
            "https://x.com/b/status/6",
            created_at=now - timedelta(hours=20),
        ),
    ]

    result = await process_raw_data({"OpenAI": tweets}, [], PipelineConfig(), None)

    assert result.stats["tweet_clusters"] == 2


@pytest.mark.asyncio
async def test_pipeline_avoids_chain_merge_between_different_events() -> None:
    tweets = [
        _tweet("OpenAI and Microsoft discuss AI infrastructure", "https://x.com/a/status/7"),
        _tweet(
            "OpenAI Microsoft Anthropic Claude AI infrastructure roundup",
            "https://x.com/b/status/8",
        ),
        _tweet("Anthropic and Claude publish Gemini AI notes", "https://x.com/c/status/9"),
    ]

    result = await process_raw_data({"AI": tweets}, [], PipelineConfig(), None)

    assert result.stats["tweet_clusters"] == 2


def _tweet(
    text: str,
    url: str,
    retweets: int = 1,
    created_at: datetime | None = None,
) -> RawTweet:
    created = created_at or datetime.now(UTC)
    return RawTweet(
        author="@OpenAI",
        text=text,
        likes=2,
        retweets=retweets,
        replies=0,
        views=500,
        created_at=created.strftime("%a %b %d %H:%M:%S +0000 %Y"),
        url=url,
    )
