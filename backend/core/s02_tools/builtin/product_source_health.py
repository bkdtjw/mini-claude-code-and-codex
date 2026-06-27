from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .product_source_health_models import (
    ProductSourceHealthArgs,
    ProductSourceHealthConfig,
    ProductSourceHealthError,
)
from .product_source_health_probe import (
    format_product_source_health,
    run_product_source_health,
)


def create_product_source_health_tool(
    config: ProductSourceHealthConfig | None = None,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    resolved = config or ProductSourceHealthConfig()
    definition = ToolDefinition(
        name="product_source_health_check",
        description=(
            "Check Taobao affiliate product data-source health before coupon/product queries. "
            "Distinguishes external source timeout/errors from true no-coupon/no-result cases."
        ),
        category="search",
        parameters=ToolParameterSchema(
            properties={
                "q": {"type": "string", "description": "健康检查关键词，默认 纸巾"},
                "check_brand_pool": {"type": "boolean", "description": "是否检查精选品牌池"},
                "check_detail": {"type": "boolean", "description": "是否用搜索结果继续检查详情查券"},
                "only_coupon": {"type": "boolean", "description": "是否只检查有券商品，默认 true"},
                "max_results": {"type": "integer", "description": "每个探测最多取 1-3 条，默认 1"},
            },
            required=[],
        ),
        side_effect=False,
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            params = _parse_args(args)
            probes = await run_product_source_health(params, resolved)
            return ToolResult(output=format_product_source_health(probes))
        except (ProductSourceHealthError, ValidationError, ValueError) as exc:
            return ToolResult(output=f"商品数据源健康检查失败：{exc}", is_error=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"商品数据源健康检查异常：{exc}", is_error=True)

    return definition, execute


def _parse_args(args: dict[str, Any]) -> ProductSourceHealthArgs:
    try:
        return ProductSourceHealthArgs.model_validate(args)
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "参数不合法")
        raise ProductSourceHealthError(f"参数错误：{message}") from exc


__all__ = [
    "ProductSourceHealthArgs",
    "ProductSourceHealthConfig",
    "create_product_source_health_tool",
]
