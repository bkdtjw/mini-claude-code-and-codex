from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import product_source_health_probe as probe
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.product_source_health import create_product_source_health_tool
from backend.core.s02_tools.builtin.product_source_health_models import ProductSourceHealthConfig
from backend.core.s02_tools.builtin.zhetaoke_brand_client import ZhetaokeBrandResult
from backend.core.s02_tools.builtin.zhetaoke_client import ZhetaokeProduct
from backend.core.s02_tools.builtin.zhetaoke_search_client import ZhetaokeSearchProduct


@pytest.mark.asyncio
async def test_product_source_health_reports_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    search_item = ZhetaokeSearchProduct(
        tao_id="encrypted-id",
        title="抽纸巾",
        coupon_info="满5减3",
    )
    monkeypatch.setattr(probe, "search_taobao_products", AsyncMock(return_value=[search_item]))
    monkeypatch.setattr(
        probe,
        "fetch_brand_products",
        AsyncMock(return_value=ZhetaokeBrandResult(products=[search_item])),
    )
    monkeypatch.setattr(
        probe,
        "fetch_product_detail",
        AsyncMock(return_value=[ZhetaokeProduct(tao_id="encrypted-id", title="抽纸巾")]),
    )
    _, execute = create_product_source_health_tool(_config())

    result = await execute({"q": "纸巾"})

    assert result.is_error is False
    assert "商品数据源健康检查: healthy" in result.output
    assert "- taobao_search: OK" in result.output
    assert "- taobao_brand_pool: OK" in result.output
    assert "- taobao_detail: OK" in result.output


@pytest.mark.asyncio
async def test_product_source_health_reports_degraded_when_search_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brand_item = ZhetaokeSearchProduct(tao_id="brand-id", title="品牌商品")
    monkeypatch.setattr(probe, "search_taobao_products", AsyncMock(side_effect=TimeoutError("timeout")))
    monkeypatch.setattr(
        probe,
        "fetch_brand_products",
        AsyncMock(return_value=ZhetaokeBrandResult(products=[brand_item])),
    )
    _, execute = create_product_source_health_tool(_config())

    result = await execute({"q": "纸巾"})

    assert result.is_error is False
    assert "商品数据源健康检查: degraded" in result.output
    assert "- taobao_search: FAIL (error" in result.output
    assert "- taobao_brand_pool: OK" in result.output
    assert "- taobao_detail: FAIL (skipped" in result.output
    assert "不要误报为没有优惠券" in result.output


@pytest.mark.asyncio
async def test_product_source_health_treats_empty_brand_pool_as_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_item = ZhetaokeSearchProduct(tao_id="encrypted-id", title="抽纸巾")
    monkeypatch.setattr(probe, "search_taobao_products", AsyncMock(return_value=[search_item]))
    monkeypatch.setattr(
        probe,
        "fetch_brand_products",
        AsyncMock(return_value=ZhetaokeBrandResult(products=[])),
    )
    monkeypatch.setattr(
        probe,
        "fetch_product_detail",
        AsyncMock(return_value=[ZhetaokeProduct(tao_id="encrypted-id", title="抽纸巾")]),
    )
    _, execute = create_product_source_health_tool(_config())

    result = await execute({"q": "纸巾"})

    assert result.is_error is False
    assert "商品数据源健康检查: healthy" in result.output
    assert "- taobao_brand_pool: OK (empty" in result.output


@pytest.mark.asyncio
async def test_product_source_health_requires_zhetaoke_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("ZHETAOKE_APP_KEY", "ZHETAOKE_TB_SID", "ZHETAOKE_TB_PID"):
        monkeypatch.delenv(key, raising=False)
    _, execute = create_product_source_health_tool(ProductSourceHealthConfig())

    result = await execute({})

    assert result.is_error is True
    assert "ZHETAOKE_APP_KEY" in result.output


def test_builtin_tools_registers_product_source_health_when_internal_hidden() -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry, workspace=None, include_internal_product_tools=False)

    assert registry.has("product_search")
    assert registry.has("product_coupon_lookup")
    assert registry.has("product_source_health_check")
    assert not registry.has("zhetaoke_taobao_search")


def _config() -> ProductSourceHealthConfig:
    return ProductSourceHealthConfig(
        zhetaoke_appkey="app-key",
        zhetaoke_sid="sid",
        zhetaoke_pid="pid",
    )
