from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from backend.common.logging import get_logger

logger = get_logger(component="feishu_client")
RESOURCE_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"


async def download_message_resource(
    client_obj: Any,
    message_id: str,
    file_key: str,
    dest_path: str | Path,
) -> Path | None:
    await client_obj._ensure_token()  # noqa: SLF001
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = RESOURCE_URL.format(message_id=message_id, file_key=file_key)
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            response = await client.get(
                url,
                headers=client_obj._headers(),  # noqa: SLF001
                params={"type": "file"},
            )
        if response.status_code >= 400:
            logger.error("feishu_resource_download_error", status_code=response.status_code)
            return None
        path.write_bytes(response.content)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.error("feishu_resource_download_error", error=str(exc))
        return None


__all__ = ["download_message_resource"]
