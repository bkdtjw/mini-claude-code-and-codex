from __future__ import annotations

ZHETAOKE_EMPTY_CONTENT = "无符合条件的数据"
ZHETAOKE_NO_RESULT_NOTE = "未找到符合条件商品/优惠券，不代表 API 不可用。"

ZHETAOKE_TOOL_NOTE = (
    "折淘客是第三方联盟数据源，不是淘宝联盟官方。"
    "若 HTTP 200 但业务 status=301 且内容为“无符合条件的数据”，"
    "应解释为无商品/无券结果，不是 HTTP 跳转或整体故障。"
)

COMMERCE_TOOL_RESULT_RULES = (
    "电商工具结果解释规则：折淘客是第三方联盟数据源，不是淘宝联盟官方；"
    "HTTP 200 + 业务 status=301 + 无符合条件的数据表示无商品/无券结果；"
    "报告中写“未找到符合条件商品/优惠券”，不要解读为接口迁移或系统故障；"
    "需要判断淘宝商品源是否波动时，先调用 product_source_health_check。"
)


def is_zhetaoke_no_result(status: int, message: str) -> bool:
    return status == 301 and ZHETAOKE_EMPTY_CONTENT in message


__all__ = [
    "COMMERCE_TOOL_RESULT_RULES",
    "ZHETAOKE_EMPTY_CONTENT",
    "ZHETAOKE_NO_RESULT_NOTE",
    "ZHETAOKE_TOOL_NOTE",
    "is_zhetaoke_no_result",
]
