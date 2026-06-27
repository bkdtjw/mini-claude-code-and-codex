from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from backend.adapters.base import LLMAdapter

FeishuClient: Any = None


class HookRuntimeError(Exception):
    """Runtime seam error for Event Hooks integrations."""


class HookRuntime(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    twitter_search_fn: Any
    assess_fn: Any
    push_fn: Any
    exa_search_fn: Any = None


def build_hook_runtime(adapter: LLMAdapter, model: str) -> HookRuntime:
    from backend.config.settings import settings
    from backend.core.s02_tools.builtin.x_models import XClientConfig

    resolved_twitter_username = settings.twitter_username or os.environ.get(
        "TWITTER_USERNAME", ""
    )
    resolved_twitter_email = settings.twitter_email or os.environ.get("TWITTER_EMAIL", "")
    resolved_twitter_password = settings.twitter_password or os.environ.get(
        "TWITTER_PASSWORD", ""
    )
    x_config = XClientConfig(
        username=resolved_twitter_username,
        email=resolved_twitter_email,
        password=resolved_twitter_password,
        proxy_url=settings.twitter_proxy_url or os.environ.get("TWITTER_PROXY_URL", ""),
        cookies_file=settings.twitter_cookies_file
        or os.environ.get("TWITTER_COOKIES_FILE", "twitter_cookies.json"),
    )
    feishu_client = None
    if settings.feishu_app_id and settings.feishu_app_secret:
        feishu_client = _feishu_client_cls()(
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
        )
    exa_key = settings.exa_api_key.strip()
    exa_fn = (
        _factory("make_exa_search_fn")(exa_key, settings.exa_proxy_url)
        if exa_key
        else None
    )
    return HookRuntime(
        twitter_search_fn=_factory("make_twitter_search_fn")(x_config),
        assess_fn=_factory("make_assess_fn")(adapter, model),
        push_fn=_factory("make_push_fn")(
            feishu_client=feishu_client,
            chat_id=settings.feishu_chat_id,
            webhook_url=settings.feishu_webhook_url,
            webhook_secret=settings.feishu_webhook_secret,
        ),
        exa_search_fn=exa_fn,
    )


def _feishu_client_cls() -> Any:
    global FeishuClient
    if FeishuClient is None:
        from backend.core.s02_tools.builtin.feishu_client import FeishuClient as client_cls

        FeishuClient = client_cls
    return FeishuClient


def _factory(name: str) -> Any:
    return globals().get(name) or __getattr__(name)


def __getattr__(name: str) -> Any:
    if name == "make_assess_fn":
        from .llm import make_assess_fn as value
    elif name == "make_push_fn":
        from .push import make_push_fn as value
    elif name == "make_twitter_search_fn":
        from .twitter import make_twitter_search_fn as value
    elif name == "make_exa_search_fn":
        from .exa import make_exa_search_fn as value
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value


__all__ = [
    "HookRuntime",
    "HookRuntimeError",
    "build_hook_runtime",
    "make_assess_fn",
    "make_exa_search_fn",
    "make_push_fn",
    "make_twitter_search_fn",
]
