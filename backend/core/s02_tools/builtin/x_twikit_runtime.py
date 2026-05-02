from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

SEARCH_FEATURE_DEFAULTS: dict[str, bool] = {
    "articles_preview_enabled": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "communities_web_enable_tweet_community_results_fetch": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "post_ctas_fetch_enabled": False,
    "premium_content_api_read_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_profile_redirect_enabled": False,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "rweb_tipjar_consumption_enabled": False,
    "rweb_video_screen_enabled": False,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "verified_phone_label_enabled": False,
    "view_counts_everywhere_api_enabled": True,
}
_CHUNK_MAP_REGEX = re.compile(
    r'[A-Za-z_$][\w$]*\.u=e=>(?:""\+)?'
    r'\(\((\{.*?\})\)?\[e\]\|\|e\)\+"\."\+\(?'
    r'(\{.*?\})\)?\[e\]\+"a\.js"(?:\)|,)',
    re.DOTALL,
)
_FEATURE_NAME_REGEX = re.compile(r'"([^"]+)"')
_MAIN_BUNDLE_REGEX = re.compile(r"responsive-web/client-web/main\.[^\"']+\.js")
_NAME_PAIR_REGEX = re.compile(r'(\d+):"([^"]+)"')
_OLD_ONDEMAND_REGEX = re.compile(r"""['|"]ondemand\.s['|"]:\s*['|"]([\w]*)['|"]""")
_SEARCH_TIMELINE_REGEX = re.compile(
    r'queryId:"([A-Za-z0-9_-]{20,})",operationName:"SearchTimeline".*?featureSwitches:\[(.*?)\]',
    re.DOTALL,
)


class SearchTimelineMetadata(BaseModel):
    bundle_url: str
    query_id: str
    feature_switches: list[str]


def build_ondemand_chunk_url(page_html: str) -> str | None:
    old_match = _OLD_ONDEMAND_REGEX.search(page_html)
    if old_match:
        return f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{old_match.group(1)}a.js"
    chunk_match = _CHUNK_MAP_REGEX.search(page_html)
    if not chunk_match:
        return None
    names = dict(_NAME_PAIR_REGEX.findall(chunk_match.group(1)))
    hashes = dict(_NAME_PAIR_REGEX.findall(chunk_match.group(2)))
    target_id = next((key for key, value in names.items() if value == "ondemand.s"), None)
    target_hash = hashes.get(target_id or "")
    if not target_hash:
        return None
    return f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{target_hash}a.js"


def dedupe_cookie_container(container: Any) -> None:
    if not hasattr(container, "cookies") or not hasattr(container.cookies, "jar"):
        return
    unique: dict[str, str] = {}
    for cookie in container.cookies.jar:
        if cookie.name not in unique:
            unique[cookie.name] = cookie.value
    container.cookies = list(unique.items())


def extract_main_bundle_path(page_text: str) -> str:
    match = _MAIN_BUNDLE_REGEX.search(page_text)
    if not match:
        raise ValueError("Could not find main.js bundle on x.com homepage")
    return match.group(0)


def parse_search_timeline_metadata(bundle_text: str, bundle_url: str) -> SearchTimelineMetadata:
    match = _SEARCH_TIMELINE_REGEX.search(bundle_text)
    if not match:
        raise ValueError("Could not find SearchTimeline metadata in main.js")
    return SearchTimelineMetadata(
        bundle_url=bundle_url,
        query_id=match.group(1),
        feature_switches=_FEATURE_NAME_REGEX.findall(match.group(2)),
    )


__all__ = [
    "SEARCH_FEATURE_DEFAULTS",
    "SearchTimelineMetadata",
    "build_ondemand_chunk_url",
    "dedupe_cookie_container",
    "extract_main_bundle_path",
    "parse_search_timeline_metadata",
]
