from __future__ import annotations

from backend.core.system_prompt import build_system_prompt


def test_system_prompt_includes_commerce_result_rules_for_sub_agents() -> None:
    prompt = build_system_prompt("/workspace")

    assert "电商工具结果解释规则" in prompt
    assert "status=301" in prompt
    assert "未找到符合条件商品/优惠券" in prompt
    assert "301重定向" not in prompt
    assert "API端点变更" not in prompt
    assert "服务不可用" not in prompt


def test_system_prompt_routes_local_project_tasks_to_local_tools() -> None:
    prompt = build_system_prompt("/workspace")

    assert "当前工作目录: /workspace" in prompt
    assert "本地项目相关任务" in prompt
    assert "目录结构" in prompt
    assert "入口文件" in prompt
    assert "代码搜索" in prompt
    assert "文件读取" in prompt
    assert "命令执行" in prompt
    assert "browse_web 是浏览器自动化工具" in prompt


def test_system_prompt_explains_missing_workspace_for_local_project_tasks() -> None:
    prompt = build_system_prompt(None)

    assert "当前没有选择本地工作目录" in prompt
    assert "当前项目" in prompt
    assert "本地文件" in prompt
    assert "目录结构" in prompt
    assert "入口文件" in prompt
    assert "应先让用户选择工作区或提供文件内容" in prompt
    assert "不要调用网页、商品、金融等无关工具来替代本地项目工具" in prompt
