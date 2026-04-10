"""Twitter-飞书定时任务的条件注册逻辑。"""

from __future__ import annotations

import os

from backend.adapters.base import LLMAdapter
from backend.common.types import LLMRequest, Message


def register_twitter_feishu_scheduler(
    tools: list[tuple],
    feishu_url: str,
    feishu_secret: str,
    twitter_username: str,
    twitter_email: str,
    twitter_password: str,
    twitter_proxy_url: str | None,
    twitter_cookies_file: str | None,
    adapter: LLMAdapter | None,
    default_model: str,
) -> None:
    """条件注册 Twitter-飞书定时任务工具。

    需要同时配置飞书 Webhook 和 Twitter 账号才会注册。
    """
    if not feishu_url:
        return
    if not ((twitter_username or twitter_email) and twitter_password):
        return
    try:
        from .feishu_notify import _build_request_body
        from .twitter_feishu_scheduler import TwitterFeishuScheduler
        from .twitter_feishu_tools import (
            build_default_config,
            create_twitter_feishu_scheduler_tool,
        )
        from .x_client import XClientConfig, XSearchOptions, search_x_posts
    except ImportError:
        return

    x_config = XClientConfig(
        username=twitter_username,
        email=twitter_email,
        password=twitter_password,
        proxy_url=twitter_proxy_url or os.environ.get("TWITTER_PROXY_URL", ""),
        cookies_file=twitter_cookies_file
        or os.environ.get("TWITTER_COOKIES_FILE", "twitter_cookies.json"),
    )
    search_fn = _build_search_fn(x_config)
    llm_fn = _build_llm_fn(adapter, default_model)
    feishu_fn = _build_feishu_fn(feishu_url, feishu_secret, _build_request_body)

    targets_json = os.environ.get("TWITTER_FEISHU_TARGETS", "")
    cron_hour = int(os.environ.get("TWITTER_FEISHU_CRON_HOUR", "7"))
    cron_minute = int(os.environ.get("TWITTER_FEISHU_CRON_MINUTE", "0"))

    config = build_default_config(
        cron_hour=cron_hour,
        cron_minute=cron_minute,
        targets_json=targets_json,
        feishu_webhook_url=feishu_url,
        feishu_secret=feishu_secret,
    )
    scheduler = TwitterFeishuScheduler(config, search_fn, llm_fn, feishu_fn)
    tools.append(create_twitter_feishu_scheduler_tool(scheduler))


def _build_search_fn(x_config):  # noqa: ANN001
    from .x_client import XSearchOptions, search_x_posts

    async def _search(query: str, max_results: int, days: int, search_type: str) -> str:
        from .x_search import XSearchArgs, _format_report

        posts = await search_x_posts(
            query,
            x_config,
            XSearchOptions(max_results=max_results, days=days, search_type=search_type),
        )
        params = XSearchArgs(query=query, max_results=max_results, days=days)
        return _format_report(params, posts)

    return _search


def _build_llm_fn(adapter: LLMAdapter | None, default_model: str):  # noqa: ANN202
    if adapter is None or not default_model:
        return None

    async def _llm_call(system_prompt: str, user_prompt: str) -> str:
        response = await adapter.complete(
            LLMRequest(
                model=default_model,
                messages=[
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=user_prompt),
                ],
                max_tokens=8192,
            )
        )
        return response.content if response else ""

    return _llm_call


def _build_feishu_fn(feishu_url: str, feishu_secret: str, build_body_fn):  # noqa: ANN001, ANN202
    import httpx

    async def _feishu_send(title: str, content: str) -> bool:
        body = build_body_fn(content=content, title=title, secret=feishu_secret or None)
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.post(feishu_url, json=body)
            data = resp.json()
            return data.get("StatusCode", data.get("code")) == 0
        except Exception:
            return False

    return _feishu_send


__all__ = ["register_twitter_feishu_scheduler"]
