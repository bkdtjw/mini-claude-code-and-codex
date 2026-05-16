from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.config.http_client import load_http_client_config
from backend.core.s02_tools.builtin.youtube_log_filter import install_httpx_api_key_redaction

ZHETAOKE_DETAIL_URL = "http://api.zhetaoke.com:20000/api/api_detail.ashx"
install_httpx_api_key_redaction()


class ZhetaokeClientError(Exception):
    """Zhetaoke client error."""


class ZhetaokeCredentials(BaseModel):
    appkey: str


class ZhetaokeDetailRequest(BaseModel):
    tao_id: str = ""
    num_iids: str = ""
    code: str = ""
    detail_type: str = Field(default="1")

    @field_validator("detail_type")
    @classmethod
    def validate_detail_type(cls, value: str) -> str:
        cleaned = str(value or "1").strip()
        if cleaned not in {"0", "1"}:
            raise ValueError("detail_type must be 0 or 1")
        return cleaned

    @model_validator(mode="after")
    def validate_ids(self) -> ZhetaokeDetailRequest:
        self.tao_id = self.tao_id.strip()
        self.num_iids = self.num_iids.strip()
        if not self.tao_id and not self.num_iids:
            raise ValueError("tao_id or num_iids is required")
        if self.num_iids and len([item for item in self.num_iids.split(",") if item.strip()]) > 40:
            raise ValueError("num_iids supports at most 40 ids")
        return self


class ZhetaokeProduct(BaseModel):
    code: str = ""
    tao_id: str = ""
    title: str = ""
    long_title: str = ""
    intro: str = ""
    image_url: str = ""
    price: str = ""
    coupon_price: str = ""
    coupon_info: str = ""
    coupon_amount: str = ""
    coupon_start_time: str = ""
    coupon_end_time: str = ""
    commission_rate: str = ""
    commission: str = ""
    shop_title: str = ""
    item_url: str = ""
    comment_count: str = ""
    good_rate: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


async def fetch_product_detail(
    credentials: ZhetaokeCredentials,
    request: ZhetaokeDetailRequest,
    client: httpx.AsyncClient | None = None,
) -> list[ZhetaokeProduct]:
    try:
        if not credentials.appkey.strip():
            raise ZhetaokeClientError("ZHETAOKE_APP_KEY is required")
        params = _build_params(credentials, request)
        if client is not None:
            payload = await _request_json(client, params)
        else:
            async with httpx.AsyncClient(
                timeout=12.0,
                trust_env=load_http_client_config().trust_env,
            ) as http_client:
                payload = await _request_json(http_client, params)
        return [_to_product(item) for item in _extract_items(payload)]
    except ZhetaokeClientError:
        raise
    except httpx.HTTPError as exc:
        raise ZhetaokeClientError(f"折京客 API 网络请求失败：{exc.__class__.__name__}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ZhetaokeClientError(f"折京客 API 调用失败：{exc}") from exc


def _build_params(
    credentials: ZhetaokeCredentials,
    request: ZhetaokeDetailRequest,
) -> dict[str, str]:
    params = {
        "appkey": credentials.appkey.strip(),
        "tao_id": request.tao_id,
        "num_iids": request.num_iids,
        "code": request.code.strip(),
        "type": request.detail_type,
    }
    return {key: value for key, value in params.items() if value}


async def _request_json(client: httpx.AsyncClient, params: dict[str, str]) -> dict[str, Any]:
    response = await client.get(ZHETAOKE_DETAIL_URL, params=params)
    if response.status_code >= 400:
        raise ZhetaokeClientError(f"折京客 API HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ZhetaokeClientError("折京客 API 返回不是 JSON object")
    status = int(payload.get("status") or 0)
    if status != 200:
        raise ZhetaokeClientError(f"折京客 API 错误 {status}")
    return payload


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    content = payload.get("content") or []
    return [item for item in content if isinstance(item, dict)] if isinstance(content, list) else []


def _to_product(item: dict[str, Any]) -> ZhetaokeProduct:
    return ZhetaokeProduct(
        code=str(item.get("code") or ""),
        tao_id=str(item.get("tao_id") or ""),
        title=str(item.get("title") or ""),
        long_title=str(item.get("tao_title") or ""),
        intro=str(item.get("jianjie") or ""),
        image_url=str(item.get("pict_url") or ""),
        price=str(item.get("size") or ""),
        coupon_price=str(item.get("quanhou_jiage") or ""),
        coupon_info=str(item.get("coupon_info") or ""),
        coupon_amount=str(item.get("coupon_info_money") or ""),
        coupon_start_time=str(item.get("coupon_start_time") or ""),
        coupon_end_time=str(item.get("coupon_end_time") or ""),
        commission_rate=str(item.get("tkrate3") or ""),
        commission=str(item.get("tkfee3") or ""),
        shop_title=str(item.get("shop_title") or item.get("nick") or ""),
        item_url=str(item.get("item_url") or ""),
        comment_count=str(item.get("commentCount") or ""),
        good_rate=str(item.get("haopinglv") or ""),
        raw=item,
    )


__all__ = [
    "ZhetaokeClientError",
    "ZhetaokeCredentials",
    "ZhetaokeDetailRequest",
    "ZhetaokeProduct",
    "fetch_product_detail",
]
