from __future__ import annotations

import os
import time

from .product_source_health_models import (
    ProductProbeResult,
    ProductSourceHealthArgs,
    ProductSourceHealthConfig,
    ProductSourceHealthError,
)
from .zhetaoke_brand_client import ZhetaokeBrandCredentials, ZhetaokeBrandRequest, fetch_brand_products
from .zhetaoke_client import ZhetaokeCredentials, ZhetaokeDetailRequest, fetch_product_detail
from .zhetaoke_search_client import (
    ZhetaokeSearchCredentials,
    ZhetaokeSearchProduct,
    ZhetaokeSearchRequest,
    search_taobao_products,
)


async def run_product_source_health(
    args: ProductSourceHealthArgs,
    config: ProductSourceHealthConfig,
) -> list[ProductProbeResult]:
    try:
        credentials = load_credentials(config)
        probes: list[ProductProbeResult] = []
        search_probe, seed = await _probe_search(args, credentials)
        probes.append(search_probe)
        if args.check_brand_pool:
            probes.append(await _probe_brand(args, credentials))
        if args.check_detail:
            probes.append(await _probe_detail(args, credentials, seed))
        return probes
    except Exception as exc:  # noqa: BLE001
        raise ProductSourceHealthError(str(exc)) from exc


def load_credentials(config: ProductSourceHealthConfig) -> ZhetaokeSearchCredentials:
    credentials = ZhetaokeSearchCredentials(
        appkey=(config.zhetaoke_appkey or os.environ.get("ZHETAOKE_APP_KEY", "")).strip(),
        sid=(config.zhetaoke_sid or os.environ.get("ZHETAOKE_TB_SID", "")).strip(),
        pid=(config.zhetaoke_pid or os.environ.get("ZHETAOKE_TB_PID", "")).strip(),
    )
    if not credentials.appkey or not credentials.sid or not credentials.pid:
        raise ProductSourceHealthError("请配置 ZHETAOKE_APP_KEY、ZHETAOKE_TB_SID 和 ZHETAOKE_TB_PID")
    return credentials


async def _probe_search(
    args: ProductSourceHealthArgs,
    credentials: ZhetaokeSearchCredentials,
) -> tuple[ProductProbeResult, ZhetaokeSearchProduct | None]:
    started = time.perf_counter()
    try:
        products = await search_taobao_products(
            credentials,
            ZhetaokeSearchRequest(
                q=args.q,
                page_size=args.max_results,
                sort="price_asc",
                youquan="1" if args.only_coupon else "",
            ),
        )
        return _probe_from_products("taobao_search", products, started), _first(products)
    except Exception as exc:  # noqa: BLE001
        return _failed_probe("taobao_search", started, exc), None


async def _probe_brand(
    args: ProductSourceHealthArgs,
    credentials: ZhetaokeSearchCredentials,
) -> ProductProbeResult:
    started = time.perf_counter()
    try:
        result = await fetch_brand_products(
            ZhetaokeBrandCredentials(**credentials.model_dump()),
            ZhetaokeBrandRequest(page_size=args.max_results, sort="new"),
        )
        if not result.products:
            return ProductProbeResult(
                name="taobao_brand_pool",
                ok=True,
                status="empty",
                latency_ms=_elapsed_ms(started),
                detail="接口可达，但未返回精选品牌样本",
            )
        return _probe_from_products("taobao_brand_pool", result.products, started)
    except Exception as exc:  # noqa: BLE001
        return _failed_probe("taobao_brand_pool", started, exc)


async def _probe_detail(
    args: ProductSourceHealthArgs,
    credentials: ZhetaokeSearchCredentials,
    seed: ZhetaokeSearchProduct | None,
) -> ProductProbeResult:
    if seed is None or not seed.tao_id:
        return ProductProbeResult(
            name="taobao_detail",
            ok=False,
            status="skipped",
            detail="搜索未返回可用于详情探测的商品",
        )
    started = time.perf_counter()
    try:
        products = await fetch_product_detail(
            ZhetaokeCredentials(**credentials.model_dump()),
            ZhetaokeDetailRequest(tao_id=seed.tao_id, detail_type="0"),
        )
        probe = _probe_from_products("taobao_detail", products, started)
        probe.item_id = seed.tao_id
        return probe
    except Exception as exc:  # noqa: BLE001
        return _failed_probe("taobao_detail", started, exc)


def format_product_source_health(probes: list[ProductProbeResult]) -> str:
    status = overall_status(probes)
    lines = [f"商品数据源健康检查: {status}"]
    lines.extend(_format_probe(item) for item in probes)
    lines.append(_guidance(status))
    return "\n".join(lines)


def overall_status(probes: list[ProductProbeResult]) -> str:
    active = [item for item in probes if item.status != "skipped"]
    if active and all(item.ok for item in active):
        return "healthy"
    if any(item.ok for item in active):
        return "degraded"
    return "unhealthy"


def _probe_from_products(
    name: str,
    products: list[ZhetaokeSearchProduct],
    started: float,
) -> ProductProbeResult:
    seed = _first(products)
    return ProductProbeResult(
        name=name,
        ok=seed is not None,
        status="ok" if seed else "empty",
        latency_ms=_elapsed_ms(started),
        detail=_product_detail(seed),
        item_id=seed.tao_id if seed else "",
    )


def _failed_probe(name: str, started: float, exc: Exception) -> ProductProbeResult:
    return ProductProbeResult(
        name=name,
        ok=False,
        status="error",
        latency_ms=_elapsed_ms(started),
        detail=f"{exc.__class__.__name__}: {exc}",
    )


def _format_probe(probe: ProductProbeResult) -> str:
    label = "OK" if probe.ok else "FAIL"
    latency = f"{probe.latency_ms}ms" if probe.latency_ms else "未执行"
    return f"- {probe.name}: {label} ({probe.status}, {latency}) {probe.detail}".rstrip()


def _guidance(status: str) -> str:
    if status == "healthy":
        return "建议: 淘宝商品/优惠券查询可正常使用。"
    if status == "degraded":
        return "建议: 部分数据源异常，回答时说明外部商品源波动，不要误报为没有优惠券。"
    return "建议: 暂停淘宝商品/优惠券查询，提示外部商品源暂不可用。"


def _product_detail(product: ZhetaokeSearchProduct | None) -> str:
    if product is None:
        return "未返回商品数据"
    coupon = product.coupon_info or "无券信息"
    title = product.title or product.long_title or "未命名商品"
    return f"返回商品 {title[:40]}，优惠券 {coupon[:40]}"


def _first(products: list[ZhetaokeSearchProduct]) -> ZhetaokeSearchProduct | None:
    return products[0] if products else None


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


__all__ = [
    "format_product_source_health",
    "load_credentials",
    "overall_status",
    "run_product_source_health",
]
