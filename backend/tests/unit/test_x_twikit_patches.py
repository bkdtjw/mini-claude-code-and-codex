from __future__ import annotations

from typing import Any

import pytest

from backend.core.s02_tools.builtin.x_twikit_patches import (
    SEARCH_FEATURE_DEFAULTS,
    _build_ondemand_chunk_url,
    _extract_main_bundle_path,
    _patched_search_timeline,
    _parse_search_timeline_metadata,
    SearchTimelineMetadata,
)


def test_build_ondemand_chunk_url_supports_new_chunk_map() -> None:
    html = (
        'g.u=e=>(({20113:"ondemand.s",1:"bundle.A"}[e]||e)+"."+'
        '{20113:"02cffce",1:"1234567"}[e]+"a.js")'
    )
    url = _build_ondemand_chunk_url(html)
    assert url == "https://abs.twimg.com/responsive-web/client-web/ondemand.s.02cffcea.js"


def test_extract_main_bundle_path_reads_current_homepage_markup() -> None:
    html = '<script src="https://abs.twimg.com/responsive-web/client-web/main.9eef478a.js"></script>'
    assert _extract_main_bundle_path(html) == "responsive-web/client-web/main.9eef478a.js"


def test_parse_search_timeline_metadata_reads_query_id_and_features() -> None:
    bundle_text = (
        'queryId:"GcXk9vN_d1jUfHNqLacXQA",operationName:"SearchTimeline",'
        'operationType:"query",metadata:{featureSwitches:["articles_preview_enabled",'
        '"responsive_web_enhance_cards_enabled"],fieldToggles:[]}}'
    )
    metadata = _parse_search_timeline_metadata(bundle_text, "https://abs.twimg.com/main.js")
    assert metadata.query_id == "GcXk9vN_d1jUfHNqLacXQA"
    assert metadata.feature_switches == [
        "articles_preview_enabled",
        "responsive_web_enhance_cards_enabled",
    ]
    assert SEARCH_FEATURE_DEFAULTS["articles_preview_enabled"] is True


class _FakeCookies:
    jar: list[Any] = []


class _FakeHttp:
    def __init__(self) -> None:
        self.cookies = _FakeCookies()


class _FakeBase:
    def __init__(self) -> None:
        self.http = _FakeHttp()
        self._base_headers = {"x-test": "1"}
        self.last_call: dict[str, Any] | None = None

    async def post(self, url: str, **kwargs: Any) -> tuple[dict[str, str], None]:
        self.last_call = {"url": url, **kwargs}
        return {"ok": "1"}, None


class _FakeGqlClient:
    def __init__(self) -> None:
        self.base = _FakeBase()


@pytest.mark.asyncio
async def test_patched_search_timeline_uses_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_metadata(_: Any) -> SearchTimelineMetadata:
        return SearchTimelineMetadata(
            bundle_url="https://abs.twimg.com/main.js",
            query_id="GcXk9vN_d1jUfHNqLacXQA",
            feature_switches=["articles_preview_enabled"],
        )

    monkeypatch.setattr(
        "backend.core.s02_tools.builtin.x_twikit_patches._get_search_timeline_metadata",
        _fake_metadata,
    )
    gql_client = _FakeGqlClient()

    response, _ = await _patched_search_timeline(gql_client, "hello", "Latest", 2, None)

    assert response == {"ok": "1"}
    assert gql_client.base.last_call is not None
    assert gql_client.base.last_call["url"].endswith("/GcXk9vN_d1jUfHNqLacXQA/SearchTimeline")
