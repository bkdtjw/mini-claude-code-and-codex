from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_MAX_OUTPUT_CHARS = 11000

SPAM_KEYWORDS = (
    "限时优惠",
    "点击领取",
    "promo code",
    "discount",
    "giveaway",
    "airdrop",
    "free money",
    "sign up now",
    "affiliate link",
    "use my code",
    "referral",
    "🔥限时",
    "立即抢购",
    "whitelist spot",
)

ENTITY_TERMS = (
    "Google DeepMind", "Hugging Face", "HuggingFace", "Stability AI",
    "ByteDance", "OpenAI", "Anthropic", "Google", "DeepMind", "Meta AI",
    "Meta", "Microsoft", "Apple", "Amazon", "AWS", "Nvidia", "AMD", "Intel",
    "Tesla", "xAI", "Mistral", "Cohere", "Midjourney", "百度", "阿里", "腾讯",
    "字节跳动", "DeepSeek", "Moonshot", "智谱", "零一万物", "GPT-4", "GPT-4o",
    "GPT-5", "ChatGPT", "o4-mini", "o1", "o3", "Claude 4", "Claude Code",
    "Claude", "Opus", "Sonnet", "Haiku", "Gemini 2", "Gemini Pro",
    "Gemini Ultra", "Gemini", "Llama 4", "Llama 3", "Llama", "Grok",
    "GitHub Copilot", "Copilot", "Sora", "DALL-E", "Midjourney v6", "Flux",
    "Cursor", "Windsurf", "Devin", "Codex", "AGI", "ASI", "LLM", "MCP",
    "RAG", "RLHF", "DPO", "transformer", "diffusion", "fine-tuning",
    "fine tuning", "multimodal", "reasoning", "chain of thought", "CoT",
    "AI agents", "AI agent", "agentic", "open source", "open weight",
    "context window", "long context", "function calling", "tool use",
    "prompt engineering", "prompt caching", "embedding", "vector database",
    "Sam Altman", "Dario Amodei", "Demis Hassabis", "Yann LeCun",
    "Ilya Sutskever", "Andrej Karpathy", "Elon Musk", "Mark Zuckerberg",
    "Satya Nadella", "Jensen Huang",
)

STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "那", "the", "a", "an", "is", "are",
    "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "but",
    "with", "by", "from", "this", "that", "it", "as", "be", "rt", "via",
}

AUTHORITY_SCORES = {
    "openai": 100, "anthropicai": 100, "googledeepmind": 100, "metaai": 100,
    "mistralai": 100, "deepseek": 100, "huggingface": 100, "nvidiaaidev": 100,
    "stability_ai": 100, "sama": 90, "darioamodei": 90, "ylecun": 90,
    "karpathy": 90, "goodside": 75, "swyx": 75, "simonw": 75, "jimfan_": 75,
    "techcrunch": 60, "theverge": 60, "arstechnica": 60, "wired": 60,
    "venturebeat": 60, "reuters": 60, "bloomberg": 60,
}


class PipelineConfig(BaseModel):
    max_evidence_cards: int = Field(default=50, ge=1, le=200)
    max_brief_chars: int = Field(default=300, ge=80, le=600)
    max_output_chars: int = Field(default=DEFAULT_MAX_OUTPUT_CHARS, ge=500, le=11000)
    fuzzy_dedup_threshold: float = Field(default=0.4, ge=0, le=1)
    event_entity_overlap_min: int = Field(default=2, ge=1, le=10)
    event_time_window_hours: int = Field(default=12, ge=1, le=168)
    min_text_length: int = Field(default=20, ge=1, le=200)
    max_age_hours: int = Field(default=48, ge=1, le=720)
    retweet_weight: float = 3.0
    reply_weight: float = 1.5
    like_weight: float = 1.0
    min_effective_views: int = 100
    engagement_absolute_ratio: float = 0.5
    engagement_rate_ratio: float = 0.5
    engagement_rate_cap: float = 100.0
    recency_weight: float = 0.25
    engagement_weight: float = 0.20
    coverage_weight: float = 0.20
    novelty_weight: float = 0.20
    authority_weight: float = 0.15
    short_penalty_max: float = 20.0
    spam_penalty: float = 45.0
    old_penalty: float = 15.0


__all__ = [
    "AUTHORITY_SCORES",
    "ENTITY_TERMS",
    "PipelineConfig",
    "SPAM_KEYWORDS",
    "STOPWORDS",
]
