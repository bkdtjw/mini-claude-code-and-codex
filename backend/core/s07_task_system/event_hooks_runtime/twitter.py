from __future__ import annotations

from backend.core.s02_tools.builtin.x_client import XRateLimitError, search_x_posts
from backend.core.s02_tools.builtin.x_models import XClientConfig, XPost, XSearchOptions
from backend.core.s07_task_system.event_hooks import TwitterQuery, TwitterSearchFn
from backend.core.s07_task_system.event_hooks_runtime import HookRuntimeError


def make_twitter_search_fn(x_config: XClientConfig) -> TwitterSearchFn:
    async def search(query: TwitterQuery) -> list[XPost]:
        try:
            options = XSearchOptions(
                max_results=query.max_results,
                days=query.days,
                search_type=query.search_type,
            )
            return await search_x_posts(query.query, x_config, options)
        except XRateLimitError as exc:
            return list(exc.partial_posts)
        except HookRuntimeError:
            raise
        except Exception as exc:
            raise HookRuntimeError(f"HOOK_RUNTIME_TWITTER_ERROR: {exc}") from exc

    return search


__all__ = ["make_twitter_search_fn"]
