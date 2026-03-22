from __future__ import annotations

from pydantic import BaseModel, Field

from backend.common.types import ProviderType


class ProviderCreateRequest(BaseModel):
    name: str
    provider_type: ProviderType
    base_url: str
    api_key: str = ""
    default_model: str
    available_models: list[str] = Field(default_factory=list)
    is_default: bool = False
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    provider_type: ProviderType | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    available_models: list[str] | None = None
    is_default: bool | None = None
    extra_headers: dict[str, str] | None = None
    enabled: bool | None = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: ProviderType
    base_url: str
    api_key: str
    default_model: str
    available_models: list[str] = Field(default_factory=list)
    is_default: bool = False
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class ProviderListResponse(BaseModel):
    items: list[ProviderResponse] = Field(default_factory=list)


class ProviderDeleteResponse(BaseModel):
    ok: bool
    message: str


class ProviderTestResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: int


class ProviderDefaultResponse(BaseModel):
    ok: bool
    provider: ProviderResponse


__all__ = [
    "ProviderCreateRequest",
    "ProviderUpdateRequest",
    "ProviderResponse",
    "ProviderListResponse",
    "ProviderDeleteResponse",
    "ProviderTestResponse",
    "ProviderDefaultResponse",
]
