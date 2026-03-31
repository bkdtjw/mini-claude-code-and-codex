from __future__ import annotations

import re
from typing import Any

from .x_twikit_runtime import (
    SEARCH_FEATURE_DEFAULTS,
    SearchTimelineMetadata,
    build_ondemand_chunk_url,
    dedupe_cookie_container,
    extract_main_bundle_path,
    parse_search_timeline_metadata,
)

_INDICES_REGEX = re.compile(r"(\(\w{1}\[(\d{1,2})\],\s*16\))+")
_cached_metadata: SearchTimelineMetadata | None = None
_patch_applied = False


def apply_x_runtime_patches() -> None:
    global _patch_applied
    if _patch_applied:
        return
    try:
        from twikit.client.gql import GQLClient  # type: ignore[import-untyped]
        from twikit.x_client_transaction.transaction import (  # type: ignore[import-untyped]
            ClientTransaction,
        )
    except Exception:
        return
    ClientTransaction.get_indices = _patched_get_indices
    GQLClient.search_timeline = _patched_search_timeline
    _patch_applied = True


def reset_search_timeline_metadata_cache() -> None:
    global _cached_metadata
    _cached_metadata = None


async def _patched_get_indices(
    self: Any,
    home_page_response: Any,
    session: Any,
    headers: dict[str, str],
) -> tuple[int, list[int]]:
    html = str(self.validate_response(home_page_response) or self.home_page_response)
    js_url = build_ondemand_chunk_url(html)
    if not js_url:
        raise Exception("Couldn't locate ondemand.s chunk URL")
    response = await session.request(method="GET", url=js_url, headers=headers)
    dedupe_cookie_container(session)
    matches = [item.group(2) for item in _INDICES_REGEX.finditer(response.text)]
    if not matches:
        raise Exception("Couldn't get KEY_BYTE indices")
    indices = [int(item) for item in matches]
    return indices[0], indices[1:]


async def _patched_search_timeline(
    self: Any,
    query: str,
    product: str,
    count: int,
    cursor: str | None,
) -> Any:
    from twikit.client.gql import Endpoint  # type: ignore[import-untyped]
    from twikit.constants import FEATURES  # type: ignore[import-untyped]
    from twikit.utils import flatten_params  # type: ignore[import-untyped]

    dedupe_cookie_container(self.base.http)
    metadata = await _get_search_timeline_metadata(self.base)
    variables: dict[str, Any] = {
        "rawQuery": query,
        "count": count,
        "querySource": "typed_query",
        "product": product,
        "withGrokTranslatedBio": False,
    }
    if cursor is not None:
        variables["cursor"] = cursor
    features = {
        name: SEARCH_FEATURE_DEFAULTS.get(name, bool(FEATURES.get(name, False)))
        for name in metadata.feature_switches
    }
    url = Endpoint.url(f"{metadata.query_id}/SearchTimeline")
    return await self.base.get(
        url,
        params=flatten_params({"variables": variables, "features": features}),
        headers=self.base._base_headers,
    )


def _build_ondemand_chunk_url(page_html: str) -> str | None:
    return build_ondemand_chunk_url(page_html)


async def _get_search_timeline_metadata(base: Any) -> SearchTimelineMetadata:
    global _cached_metadata
    page_text = await _fetch_text(base, "https://x.com")
    bundle_path = _extract_main_bundle_path(page_text)
    bundle_url = f"https://abs.twimg.com/{bundle_path}"
    if _cached_metadata is not None and _cached_metadata.bundle_url == bundle_url:
        return _cached_metadata
    bundle_text = await _fetch_text(base, bundle_url)
    _cached_metadata = _parse_search_timeline_metadata(bundle_text, bundle_url)
    return _cached_metadata


async def _fetch_text(base: Any, url: str) -> str:
    headers = {
        "Accept-Language": f"{base.language},{base.language.split('-')[0]};q=0.9",
        "Cache-Control": "no-cache",
        "Referer": "https://x.com",
        "User-Agent": base._user_agent,
    }
    response = await base.http.request("GET", url, headers=headers)
    dedupe_cookie_container(base.http)
    return response.text


def _extract_main_bundle_path(page_text: str) -> str:
    return extract_main_bundle_path(page_text)


def _parse_search_timeline_metadata(bundle_text: str, bundle_url: str) -> SearchTimelineMetadata:
    return parse_search_timeline_metadata(bundle_text, bundle_url)


__all__ = [
    "SearchTimelineMetadata",
    "SEARCH_FEATURE_DEFAULTS",
    "_build_ondemand_chunk_url",
    "_extract_main_bundle_path",
    "_parse_search_timeline_metadata",
    "apply_x_runtime_patches",
    "reset_search_timeline_metadata_cache",
]
