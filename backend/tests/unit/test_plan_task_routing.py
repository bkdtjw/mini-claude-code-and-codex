from __future__ import annotations

from backend.core.s01_agent_loop.plan_task_routing import PlanTaskKind, route_plan_task


def test_routes_code_task_to_recon() -> None:
    route = route_plan_task("修复 product_search 报错并补测试")
    assert route.task_kind == PlanTaskKind.CODE
    assert route.used_recon is True


def test_routes_coupon_lookup_to_commerce_research() -> None:
    route = route_plan_task("帮我看看衣架优惠券，返回5个")
    assert route.task_kind == PlanTaskKind.COMMERCE_RESEARCH
    assert route.used_recon is False


def test_routes_dorm_light_research_away_from_code_recon() -> None:
    route = route_plan_task("调研便宜好用的宿舍帐篷灯，可以联网搜索")
    assert route.task_kind in {PlanTaskKind.COMMERCE_RESEARCH, PlanTaskKind.WEB_RESEARCH}
    assert route.used_recon is False
