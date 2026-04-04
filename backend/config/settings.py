import os
import sys

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    enable_tool_search: bool = True
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./data/agent_studio.db"
    auth_secret: str = "change-me-in-production"
    feishu_webhook_url: str = ""
    feishu_webhook_secret: str = ""
    mihomo_api_url: str = "http://127.0.0.1:9090"
    mihomo_secret: str = ""
    mihomo_path: str = ""
    mihomo_config_path: str = ""
    mihomo_work_dir: str = ""
    mihomo_sub_path: str = ""
    youtube_api_key: str = ""
    youtube_proxy_url: str = ""
    twitter_username: str = ""
    twitter_email: str = ""
    twitter_password: str = ""
    twitter_proxy_url: str = ""
    twitter_cookies_file: str = "twitter_cookies.json"

    model_config = {
        "env_file": os.path.join(
            os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ".",
            ".env",
        ),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
