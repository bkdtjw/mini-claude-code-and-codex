from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime

from .config import AUTHORITY_SCORES, PipelineConfig, SPAM_KEYWORDS
from .models import RawTweet, TaskMemory, TweetCandidate, TweetCluster
from .text import entity_overlap, extract_entities, handle_from_author, hours_ago
from .text import parse_created_at, similarity, tokenize


def build_tweet_candidates(
    tweets: dict[str, list[RawTweet]],
    config: PipelineConfig,
    memory: TaskMemory | None,
) -> list[TweetCandidate]:
    candidates = _merge_by_url(tweets)
    now = datetime.now(UTC)
    for candidate in candidates:
        candidate.tokens = tokenize(candidate.text)
        candidate.entities = extract_entities(candidate.text)
        candidate.created_dt = parse_created_at(candidate.created_at)
        candidate.hours_ago = hours_ago(candidate.created_dt, now)
        candidate.penalties = _penalties(candidate, config)
        candidate.engagement_raw = _engagement_raw(candidate, config)
    _assign_engagement_percentiles(candidates)
    for candidate in candidates:
        candidate.score_parts = _score_parts(candidate, config, memory)
        candidate.score = _weighted_score(candidate, config)
    return candidates


def build_clusters(
    candidates: list[TweetCandidate],
    config: PipelineConfig,
) -> list[TweetCluster]:
    clusters: list[TweetCluster] = []
    for candidate in candidates:
        cluster = _find_cluster(candidate, clusters, config)
        if cluster is None:
            cluster = TweetCluster(
                cluster_id=f"x_{len(clusters) + 1:03d}",
                signature=_candidate_signature(candidate),
            )
            clusters.append(cluster)
        cluster.items.append(candidate)
        cluster.entities = _union(cluster.entities, candidate.entities)
        cluster.keyword_hits = _union(cluster.keyword_hits, candidate.keyword_hits)
    for cluster in clusters:
        cluster.items.sort(key=lambda item: item.score, reverse=True)
        cluster.signature = _cluster_signature(cluster)
        cluster.score = _cluster_score(cluster)
    return sorted(clusters, key=lambda item: item.score, reverse=True)


def _merge_by_url(tweets: dict[str, list[RawTweet]]) -> list[TweetCandidate]:
    by_url: dict[str, TweetCandidate] = {}
    fallback_index = 0
    for keyword, items in tweets.items():
        for tweet in items:
            url = tweet.url or f"missing-url-{fallback_index}"
            fallback_index += 1
            candidate = by_url.get(url)
            if candidate is None:
                by_url[url] = _candidate_from_tweet(tweet, keyword, url)
                continue
            candidate.keyword_hits = _union(candidate.keyword_hits, [keyword])
            _keep_richer_candidate(candidate, tweet)
    return list(by_url.values())


def _candidate_from_tweet(tweet: RawTweet, keyword: str, url: str) -> TweetCandidate:
    return TweetCandidate(
        author=tweet.author, text=tweet.text, likes=tweet.likes,
        retweets=tweet.retweets, replies=tweet.replies, views=tweet.views,
        created_at=tweet.created_at, url=url, keyword_hits=[keyword],
    )


def _keep_richer_candidate(candidate: TweetCandidate, tweet: RawTweet) -> None:
    if len(tweet.text) > len(candidate.text):
        candidate.text = tweet.text
    candidate.likes = max(candidate.likes, tweet.likes)
    candidate.retweets = max(candidate.retweets, tweet.retweets)
    candidate.replies = max(candidate.replies, tweet.replies)
    candidate.views = max(candidate.views, tweet.views)


def _engagement_raw(candidate: TweetCandidate, config: PipelineConfig) -> float:
    weighted = (
        candidate.retweets * config.retweet_weight
        + candidate.replies * config.reply_weight
        + candidate.likes * config.like_weight
    )
    absolute = math.log10(weighted + 1) * 20
    effective_views = max(candidate.views, config.min_effective_views)
    rate = min(weighted / effective_views * 1000, config.engagement_rate_cap)
    if candidate.views <= 0:
        rate *= 0.4
    return absolute * config.engagement_absolute_ratio + rate * config.engagement_rate_ratio


def _assign_engagement_percentiles(candidates: list[TweetCandidate]) -> None:
    if not candidates:
        return
    ranked = sorted(candidates, key=lambda item: item.engagement_raw)
    denominator = max(len(ranked) - 1, 1)
    for index, candidate in enumerate(ranked):
        candidate.engagement_percentile = round(index / denominator * 100, 2)


def _score_parts(
    candidate: TweetCandidate,
    config: PipelineConfig,
    memory: TaskMemory | None,
) -> dict[str, float]:
    reported_ids = set(memory.reported_ids if memory else [])
    reported_signatures = set(memory.reported_signatures if memory else [])
    signature = _candidate_signature(candidate)
    novelty = 10.0 if candidate.url in reported_ids or signature in reported_signatures else 100.0
    return {"recency": max(0.0, 100.0 - candidate.hours_ago * 4),
            "engagement": candidate.engagement_percentile,
            "coverage": min(len(candidate.keyword_hits) * 30.0, 100.0),
            "novelty": novelty,
            "authority": float(AUTHORITY_SCORES.get(handle_from_author(candidate.author), 40))}


def _weighted_score(candidate: TweetCandidate, config: PipelineConfig) -> float:
    parts = candidate.score_parts
    score = (
        parts["recency"] * config.recency_weight
        + parts["engagement"] * config.engagement_weight
        + parts["coverage"] * config.coverage_weight
        + parts["novelty"] * config.novelty_weight
        + parts["authority"] * config.authority_weight
    )
    return round(max(score - sum(candidate.penalties.values()), 0), 2)


def _penalties(candidate: TweetCandidate, config: PipelineConfig) -> dict[str, float]:
    penalties: dict[str, float] = {}
    if len(candidate.text) < config.min_text_length:
        missing = config.min_text_length - len(candidate.text)
        penalties["short"] = min(config.short_penalty_max, float(missing))
    if candidate.hours_ago > config.max_age_hours:
        penalties["old"] = config.old_penalty
    spam_hits = [item for item in SPAM_KEYWORDS if item.lower() in candidate.text.lower()]
    if spam_hits:
        penalties["spam"] = config.spam_penalty
    return penalties


def _find_cluster(
    candidate: TweetCandidate,
    clusters: list[TweetCluster],
    config: PipelineConfig,
) -> TweetCluster | None:
    for cluster in clusters:
        anchor = cluster.items[0] if cluster.items else None
        if anchor is not None and _same_event(candidate, anchor, config):
            return cluster
    return None


def _same_event(left: TweetCandidate, right: TweetCandidate, config: PipelineConfig) -> bool:
    if abs(left.hours_ago - right.hours_ago) > config.event_time_window_hours:
        return False
    score = similarity(
        left.tokens, right.tokens, left.entities, right.entities, config.event_entity_overlap_min
    )
    if score >= config.fuzzy_dedup_threshold:
        return True
    overlap = entity_overlap(left.entities, right.entities, config.event_entity_overlap_min)
    return overlap > 0 and abs(left.hours_ago - right.hours_ago) <= config.event_time_window_hours


def _cluster_score(cluster: TweetCluster) -> float:
    best = cluster.items[0].score if cluster.items else 0
    sources = {handle_from_author(item.author) or item.author for item in cluster.items}
    source_diversity = min(len(sources) * 25.0, 100.0)
    entity_richness = min(len(cluster.entities) * 20.0, 100.0)
    return round(best * 0.75 + source_diversity * 0.15 + entity_richness * 0.10, 2)


def _candidate_signature(candidate: TweetCandidate) -> str:
    date = candidate.created_dt.date().isoformat() if candidate.created_dt else "unknown-date"
    anchors = candidate.entities[:4] or candidate.tokens[:4] or [candidate.url]
    return "|".join([*sorted(anchors), date])


def _cluster_signature(cluster: TweetCluster) -> str:
    primary = cluster.items[0] if cluster.items else None
    date = primary.created_dt.date().isoformat() if primary and primary.created_dt else "unknown-date"
    anchors = cluster.entities[:4] or (primary.tokens[:4] if primary else [cluster.cluster_id])
    return "|".join([*sorted(anchors), date])


def _union(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))
