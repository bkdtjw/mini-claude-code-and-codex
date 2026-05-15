from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from backend.adapters.role_router import RoleRouter
from backend.common.logging import get_logger
from backend.core.s02_tools.builtin.browser import smart_browse

from .action_tools import BROWSER_ACTION_TOOLS
from .controller import BrowserController
from .decision import SYSTEM_PROMPT_MAIN, main_agent_decide
from .evidence import save_evidence_screenshot
from .human_gate import human_intervention_content, needs_human_intervention
from .login_detection import should_assist_login, site_label
from .login_vision import LoginVisionHelper
from .main_agent_support import append_history, last_action_kind, result, task_hint
from .models import (
    ActionKind,
    BrowserAction,
    BrowserAgentConfig,
    BrowserAgentResult,
)
from .provider_errors import is_provider_rejection, provider_rejection_content
from .stuck_detector import StuckDetector
from .vision_subagent import VisionRequest, observe

if TYPE_CHECKING:
    from backend.storage.asset_store import AssetStore

logger = get_logger(component="browser_agent_loop")


async def run_browser_agent(
    config: BrowserAgentConfig,
    role_router: RoleRouter,
    asset_store: AssetStore | None = None,
    login_assistant: Any | None = None,
) -> BrowserAgentResult:
    history: list[dict[str, Any]] = []
    screenshots = []
    last_screenshot = b""
    last_url = ""
    started = time.monotonic()
    try:
        async with smart_browse(
            user_id=config.user_id,
            domain=config.domain,
            viewport=config.viewport,
        ) as page:
            controller = BrowserController(page)
            detector = StuckDetector(window=3)
            if config.initial_url:
                await controller.goto(config.initial_url)
            for step in range(config.max_steps):
                if time.monotonic() - started > config.timeout_seconds:
                    return result(False, "timeout", step, history, screenshots)
                screenshot = await controller.take_screenshot()
                current_url = str(getattr(page, "url", ""))
                last_screenshot, last_url = screenshot, current_url
                current_title = await page.title()
                last_kind = last_action_kind(history)
                if detector.is_stuck(current_url, screenshot, last_kind):
                    return result(False, "stuck", step, history, screenshots)
                observation = await observe(
                    VisionRequest(
                        screenshot=screenshot,
                        url=current_url,
                        title=current_title,
                        viewport=config.viewport,
                        task_hint=task_hint(config),
                        last_action_kind=last_kind,
                    ),
                    role_router,
                    config.vision_subagent_provider_id,
                )
                if login_assistant is not None and should_assist_login(
                    config, observation, current_url
                ):
                    assist_result = await login_assistant.assist(
                        page,
                        site_label(config),
                        observation.screenshot_reason or observation.page_summary,
                        vision_helper=LoginVisionHelper(
                            role_router,
                            config.vision_subagent_provider_id,
                            config.viewport,
                        ),
                    )
                    if assist_result.status == "success":
                        continue
                    current_url = str(getattr(page, "url", current_url))
                    screenshot = await controller.take_screenshot()
                    action = BrowserAction(kind=ActionKind.SCREENSHOT, reason=assist_result.status)
                    exec_result = await save_evidence_screenshot(
                        asset_store, screenshots, current_url, screenshot
                    )
                    append_history(history, step, current_url, observation, action, exec_result)
                    return result(
                        False,
                        "need_human",
                        step + 1,
                        history,
                        screenshots,
                        f"登录未完成：{assist_result.detail or assist_result.status}",
                    )
                if needs_human_intervention(observation, current_url):
                    action = BrowserAction(
                        kind=ActionKind.SCREENSHOT,
                        reason=observation.screenshot_reason or "need_human",
                    )
                    exec_result = await save_evidence_screenshot(
                        asset_store, screenshots, current_url, screenshot
                    )
                    append_history(history, step, current_url, observation, action, exec_result)
                    return result(
                        False,
                        "need_human",
                        step + 1,
                        history,
                        screenshots,
                        human_intervention_content(observation),
                    )
                action = await main_agent_decide(
                    config.task,
                    history,
                    current_url,
                    current_title,
                    observation,
                    role_router,
                    config.main_agent_provider_id,
                    config.site_guide,
                )
                if action.kind == ActionKind.DONE:
                    return result(True, "done", step + 1, history, screenshots, action.value)
                if action.kind == ActionKind.FAIL:
                    return result(False, action.reason or "fail", step + 1, history, screenshots)
                exec_result = (
                    await save_evidence_screenshot(asset_store, screenshots, current_url, screenshot)
                    if action.kind == ActionKind.SCREENSHOT
                    else await controller.execute(action)
                )
                append_history(history, step, current_url, observation, action, exec_result)
            return result(False, "max_steps", config.max_steps, history, screenshots)
    except Exception as exc:  # noqa: BLE001
        if is_provider_rejection(exc):
            if last_screenshot:
                await save_evidence_screenshot(asset_store, screenshots, last_url, last_screenshot)
            logger.warning("browser_agent_provider_rejected", error=str(exc))
            return result(
                False,
                "provider_rejected",
                len(history),
                history,
                screenshots,
                provider_rejection_content(exc),
            )
        logger.warning("browser_agent_loop_failed", error=str(exc))
        return result(False, "error", len(history), history, screenshots, str(exc))


__all__ = ["BROWSER_ACTION_TOOLS", "SYSTEM_PROMPT_MAIN", "main_agent_decide", "run_browser_agent"]
