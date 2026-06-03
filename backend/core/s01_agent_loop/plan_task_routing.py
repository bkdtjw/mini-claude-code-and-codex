from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel


class PlanTaskKind(str, Enum):  # noqa: UP042
    CODE = "code"
    COMMERCE_RESEARCH = "commerce_research"
    WEB_RESEARCH = "web_research"
    GENERAL = "general"


class PlanRoute(BaseModel):
    task_kind: PlanTaskKind
    used_recon: bool
    reason: str


_CODE_PATH_RE = re.compile(
    r"(^|[\s`])(?:backend|frontend|src|tests|scripts|config|docs)/[\w./-]+"
)
_CODE_FILE_RE = re.compile(
    r"(^|[\s`])[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|md|toml|ya?ml|json)(?=$|[\s`:，。])"
)
_CODE_IDENTIFIER_RE = re.compile(r"\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b")
_CODE_TERMS = (
    "实现",
    "修复",
    "重构",
    "代码",
    "单测",
    "测试",
    "报错",
    "异常",
    "函数",
    "类",
    "模块",
    "接口",
)
_CODE_WORDS = (
    "pytest",
    "test",
    "tests",
    "fix",
    "implement",
    "implementation",
    "refactor",
    "bug",
    "traceback",
    "commit",
    "pull request",
)
_COMMERCE_TERMS = (
    "商品",
    "优惠券",
    "券后",
    "领券",
    "折扣",
    "价格",
    "便宜",
    "购买",
    "下单",
    "淘宝",
    "天猫",
    "京东",
    "拼多多",
    "折淘客",
    "zhetaoke",
    "店铺",
    "销量",
    "大牌",
    "好用",
    "衣架",
    "挂灯",
    "帐篷灯",
    "宿舍",
)
_WEB_RESEARCH_TERMS = (
    "调研",
    "联网",
    "搜索",
    "资料",
    "新闻",
    "推荐",
    "整理",
    "对比",
    "看看",
)


def route_plan_task(user_message: str) -> PlanRoute:
    text = user_message.casefold().strip()
    if _looks_like_code_task(text):
        return PlanRoute(
            task_kind=PlanTaskKind.CODE,
            used_recon=True,
            reason="命中代码、文件、测试或修复类信号，使用仓库侦察规划",
        )
    if _contains_any(text, _COMMERCE_TERMS):
        return PlanRoute(
            task_kind=PlanTaskKind.COMMERCE_RESEARCH,
            used_recon=False,
            reason="命中商品、优惠券、价格或购买类信号，跳过代码侦察",
        )
    if _contains_any(text, _WEB_RESEARCH_TERMS):
        return PlanRoute(
            task_kind=PlanTaskKind.WEB_RESEARCH,
            used_recon=False,
            reason="命中联网调研或资料整理类信号，跳过代码侦察",
        )
    return PlanRoute(
        task_kind=PlanTaskKind.GENERAL,
        used_recon=False,
        reason="未命中代码任务信号，使用轻量任务规划",
    )


def _looks_like_code_task(text: str) -> bool:
    if _CODE_PATH_RE.search(text) or _CODE_FILE_RE.search(text):
        return True
    if _contains_any(text, _CODE_TERMS) or _contains_word(text, _CODE_WORDS):
        return True
    return bool(_CODE_IDENTIFIER_RE.search(text) and _contains_word(text, _CODE_WORDS))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _contains_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", text) for word in words)


__all__ = ["PlanRoute", "PlanTaskKind", "route_plan_task"]
