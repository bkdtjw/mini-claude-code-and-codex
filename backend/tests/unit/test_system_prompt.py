from __future__ import annotations

from backend.common.types import ToolDefinition, ToolParameterSchema
from backend.core.system_prompt import build_runtime_context, build_system_prompt


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="tool",
        category="search",
        parameters=ToolParameterSchema(),
    )


def test_system_prompt_is_stable_kernel_only() -> None:
    prompt = build_system_prompt()

    assert "你是一个编程助手" in prompt
    assert "当前工作目录" not in prompt
    assert "电商工具结果解释规则" not in prompt
    assert "压缩时按以下优先级保留信息" not in prompt


def test_runtime_context_routes_local_project_tasks_to_local_tools() -> None:
    prompt = build_runtime_context("/workspace", [_tool("Read")])

    assert "当前工作目录: /workspace" in prompt
    assert "本地项目相关任务" in prompt
    assert "browse_web 是浏览器自动化工具" in prompt


def test_runtime_context_explains_missing_workspace_for_local_project_tasks() -> None:
    prompt = build_runtime_context(None, [_tool("Read")])

    assert "当前没有选择工作目录" in prompt
    assert "本地文件" in prompt
    assert "应先让用户选择工作区" in prompt


def test_runtime_context_injects_commerce_rules_only_for_commerce_tools() -> None:
    plain = build_runtime_context("/workspace", [_tool("Read")])
    commerce = build_runtime_context("/workspace", [_tool("product_coupon_lookup")])

    assert "电商工具结果解释规则" not in plain
    assert "电商工具结果解释规则" in commerce
    assert "status=301" in commerce
    assert "未找到符合条件商品/优惠券" in commerce
