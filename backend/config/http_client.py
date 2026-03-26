from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class HttpClientConfig(BaseModel):
    trust_env: bool = False


def load_http_client_config() -> HttpClientConfig:
    path = Path(__file__).with_name("http_client.json")
    try:
        if not path.exists():
            return HttpClientConfig()
        data = json.loads(path.read_text(encoding="utf-8"))
        return HttpClientConfig.model_validate(data)
    except Exception:
        return HttpClientConfig()


__all__ = ["HttpClientConfig", "load_http_client_config"]
