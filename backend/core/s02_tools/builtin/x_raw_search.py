from __future__ import annotations

from collections.abc import Callable

from twikit import Client  # type: ignore[import-not-found, import-untyped]

from .x_models import XPost, XSearchOptions
from .x_search_response import extract_search_posts
from .x_twikit_patches import reset_search_timeline_metadata_cache


async def search_raw_posts(
    client: Client,
    query: str,
    options: XSearchOptions,
    build_query: Callable[[str, int], str],
    dedupe_client_cookies: Callable[[Client], None],
) -> list[XPost]:
    posts: list[XPost] = []
    cursor: str | None = None
    full_query = build_query(query, options.days)
    while len(posts) < options.max_results:
        response_data = await search_timeline_with_retry(
            client,
            full_query,
            options.search_type,
            min(options.max_results - len(posts), 20),
            cursor,
            dedupe_client_cookies,
        )
        batch, cursor = extract_search_posts(response_data, options.max_results - len(posts))
        posts.extend(batch)
        if not cursor or not batch:
            break
    return posts[: options.max_results]


async def search_timeline_with_retry(
    client: Client,
    query: str,
    search_type: str,
    count: int,
    cursor: str | None,
    dedupe_client_cookies: Callable[[Client], None],
) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response, _ = await client.gql.search_timeline(query, search_type, count, cursor)
            return response
        except Exception as exc:
            if 'status: 404, message: ""' not in str(exc):
                raise
            last_error = exc
            reset_search_timeline_metadata_cache()
            dedupe_client_cookies(client)
    if last_error is not None:
        raise last_error
    raise RuntimeError("SearchTimeline retry failed without an exception")


def supports_raw_search(client: Client) -> bool:
    return hasattr(client, "gql") and hasattr(client.gql, "search_timeline")


__all__ = ["search_raw_posts", "search_timeline_with_retry", "supports_raw_search"]
