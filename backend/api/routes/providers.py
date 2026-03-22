from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException

from backend.adapters.provider_manager import ProviderManager
from backend.common import LLMError
from backend.common.types import ProviderConfig
from backend.schemas.provider import (
    ProviderCreateRequest,
    ProviderDefaultResponse,
    ProviderDeleteResponse,
    ProviderListResponse,
    ProviderResponse,
    ProviderTestResponse,
    ProviderUpdateRequest,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])
provider_manager = ProviderManager()


def _mask_api_key(api_key: str) -> str:
    return f"{api_key[:4]}***" if api_key else ""


def _to_response(config: ProviderConfig) -> ProviderResponse:
    return ProviderResponse(
        id=config.id,
        name=config.name,
        provider_type=config.provider_type,
        base_url=config.base_url,
        api_key=_mask_api_key(config.api_key),
        default_model=config.default_model,
        available_models=config.available_models,
        is_default=config.is_default,
        extra_headers=config.extra_headers,
        enabled=config.enabled,
    )


def _to_http_error(error: LLMError) -> HTTPException:
    status_code = 400
    if error.code == "PROVIDER_NOT_FOUND":
        status_code = 404
    if error.code == "PROVIDER_EXISTS":
        status_code = 409
    return HTTPException(status_code=status_code, detail={"code": error.code, "message": error.message})


async def _get_provider_or_404(provider_id: str) -> ProviderConfig:
    try:
        providers = await provider_manager.list_all()
        for provider in providers:
            if provider.id == provider_id:
                return provider
        raise HTTPException(status_code=404, detail={"code": "PROVIDER_NOT_FOUND", "message": f"Provider not found: {provider_id}"})
    except LLMError as exc:
        raise _to_http_error(exc) from exc


@router.post("", response_model=ProviderResponse)
async def add_provider(body: ProviderCreateRequest) -> ProviderResponse:
    try:
        return _to_response(await provider_manager.add(ProviderConfig(**body.model_dump())))
    except LLMError as exc:
        raise _to_http_error(exc) from exc


@router.get("", response_model=ProviderListResponse)
async def list_providers() -> ProviderListResponse:
    try:
        providers = await provider_manager.list_all()
        return ProviderListResponse(items=[_to_response(item) for item in providers])
    except LLMError as exc:
        raise _to_http_error(exc) from exc


@router.get("/{id}", response_model=ProviderResponse)
async def get_provider(id: str) -> ProviderResponse:
    return _to_response(await _get_provider_or_404(id))


@router.put("/{id}", response_model=ProviderResponse)
async def update_provider(id: str, body: ProviderUpdateRequest) -> ProviderResponse:
    try:
        data = body.model_dump(exclude_none=True)
        return _to_response(await provider_manager.update(id, **data))
    except LLMError as exc:
        raise _to_http_error(exc) from exc


@router.delete("/{id}", response_model=ProviderDeleteResponse)
async def delete_provider(id: str) -> ProviderDeleteResponse:
    try:
        deleted = await provider_manager.remove(id)
        if not deleted:
            raise HTTPException(status_code=404, detail={"code": "PROVIDER_NOT_FOUND", "message": f"Provider not found: {id}"})
        return ProviderDeleteResponse(ok=True, message="Provider deleted")
    except LLMError as exc:
        raise _to_http_error(exc) from exc


@router.post("/{id}/test", response_model=ProviderTestResponse)
async def test_provider(id: str) -> ProviderTestResponse:
    try:
        start = perf_counter()
        ok = await provider_manager.test_connection(id)
        latency_ms = int((perf_counter() - start) * 1000)
        return ProviderTestResponse(ok=ok, message="Connection successful" if ok else "Connection failed", latency_ms=latency_ms)
    except LLMError as exc:
        raise _to_http_error(exc) from exc


@router.put("/{id}/default", response_model=ProviderDefaultResponse)
async def set_default_provider(id: str) -> ProviderDefaultResponse:
    try:
        await provider_manager.set_default(id)
        provider = await _get_provider_or_404(id)
        return ProviderDefaultResponse(ok=True, provider=_to_response(provider))
    except LLMError as exc:
        raise _to_http_error(exc) from exc


__all__ = ["router"]
