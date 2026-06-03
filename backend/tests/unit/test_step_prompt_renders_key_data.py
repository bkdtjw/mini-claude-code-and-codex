from __future__ import annotations

from backend.core.s01_agent_loop.plan_models import PlanStep
from backend.core.s01_agent_loop.plan_step_prompt import build_step_messages
from backend.core.s01_agent_loop.step_result import StepResult, StepStatus


def test_step_prompt_renders_previous_result_key_data() -> None:
    step = PlanStep(step_id=2, title="buy", description="Use collected data.")
    previous = StepResult(
        step_id=1,
        request_id="request-1",
        status=StepStatus.DONE,
        task="collect",
        result_summary="found item",
        key_data={"item_id": "X1", "price": 1299},
    )

    _, user_message = build_step_messages(step, 2, 2, previous_results=[previous])

    assert "## 前置步骤结果" in user_message
    assert "item_id: 'X1'" in user_message
    assert "price: 1299" in user_message
    assert "输出一个 fenced JSON 块" in user_message


def test_step_prompt_includes_commerce_result_rules() -> None:
    step = PlanStep(step_id=1, title="search", description="Find coupons.")

    system_prompt, _ = build_step_messages(step, 1, 1)

    assert "电商工具结果解释规则" in system_prompt
    assert "status=301" in system_prompt
    assert "未找到符合条件商品/优惠券" in system_prompt
    assert "301重定向" not in system_prompt
    assert "API端点变更" not in system_prompt
    assert "服务不可用" not in system_prompt
