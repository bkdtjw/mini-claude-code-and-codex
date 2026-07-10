from __future__ import annotations

from backend.config.settings import settings
from backend.core.s02_tools.builtin.x_client import XPost


def engagement_score(post: XPost) -> float:
    """热度加权分：赞×w_likes + 转×w_retweets + 浏览×w_views（权重来自 settings，可调）。

    纯函数、零外部调用——排行榜与对比复用它，不产生任何额外 X 请求。
    """
    return (
        post.likes * settings.x_rank_weight_likes
        + post.retweets * settings.x_rank_weight_retweets
        + post.views * settings.x_rank_weight_views
    )


def rank_posts(posts: list[XPost]) -> list[XPost]:
    """按热度加权分降序（稳定排序，同分保留原始顺序）。不改传入列表。"""
    return sorted(posts, key=engagement_score, reverse=True)


def total_raw_engagement(posts: list[XPost]) -> int:
    """原始互动总量（赞+转+回+浏览）——给对比页展示"声量"用。"""
    return sum(post.likes + post.retweets + post.replies + post.views for post in posts)


__all__ = ["engagement_score", "rank_posts", "total_raw_engagement"]
