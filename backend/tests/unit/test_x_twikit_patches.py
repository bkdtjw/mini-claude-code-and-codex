from __future__ import annotations

from backend.core.s02_tools.builtin.x_twikit_patches import (
    SEARCH_FEATURE_DEFAULTS,
    _build_ondemand_chunk_url,
    _extract_main_bundle_path,
    _parse_search_timeline_metadata,
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
