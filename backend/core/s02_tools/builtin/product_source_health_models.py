from __future__ import annotations

from pydantic import BaseModel, Field


class ProductSourceHealthError(Exception):
    """Product source health-check error."""


class ProductSourceHealthConfig(BaseModel):
    zhetaoke_appkey: str = ""
    zhetaoke_sid: str = ""
    zhetaoke_pid: str = ""


class ProductSourceHealthArgs(BaseModel):
    q: str = "纸巾"
    check_brand_pool: bool = True
    check_detail: bool = True
    only_coupon: bool = True
    max_results: int = Field(default=1, ge=1, le=3)


class ProductProbeResult(BaseModel):
    name: str
    ok: bool
    status: str
    latency_ms: int = 0
    detail: str = ""
    item_id: str = ""


__all__ = [
    "ProductProbeResult",
    "ProductSourceHealthArgs",
    "ProductSourceHealthConfig",
    "ProductSourceHealthError",
]
