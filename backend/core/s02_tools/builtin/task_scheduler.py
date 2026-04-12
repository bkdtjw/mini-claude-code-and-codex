from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from backend.core.s07_task_system.executor import TaskExecutor
from backend.core.s07_task_system.models import (
    NotifyConfig,
    OutputConfig,
    ScheduledTask,
)
from backend.core.s07_task_system.store import TaskStore


def create_task_tools(
    store: TaskStore,
    scheduler: None,
    executor: TaskExecutor,
) -> list[tuple[ToolDefinition, ToolExecuteFn]]:
    return [
        _create_add_task(store),
        _create_list_tasks(store),
        _create_update_task(store),
        _create_remove_task(store),
        _create_run_task_now(store, executor),
    ]


def _create_add_task(store: TaskStore) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="add_scheduled_task",
        description="Create a new scheduled task that runs on a cron schedule",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "name": {"type": "string", "description": "Task name, e.g. '推特AI日报'"},
                "cron": {"type": "string", "description": "Cron expression in Beijing time, e.g. '0 7 * * *'"},
                "prompt": {"type": "string", "description": "Full prompt to send to the agent when task fires"},
                "notify_feishu": {"type": "boolean", "description": "Whether to send result to Feishu, default true"},
                "feishu_webhook_url": {"type": "string", "description": "Custom Feishu webhook URL, leave empty for global"},
                "feishu_title": {"type": "string", "description": "Feishu message title, leave empty for task name"},
                "save_markdown": {"type": "boolean", "description": "Whether to save output as markdown file, default false"},
            },
            required=["name", "cron", "prompt"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            task = ScheduledTask(
                name=str(args["name"]),
                cron=str(args["cron"]),
                prompt=str(args["prompt"]),
                notify=NotifyConfig(
                    feishu=args.get("notify_feishu", True),
                    feishu_webhook_url=str(args.get("feishu_webhook_url", "")),
                    feishu_title=str(args.get("feishu_title", "")),
                ),
                output=OutputConfig(
                    save_markdown=bool(args.get("save_markdown", False)),
                ),
                created_at=datetime.now(),
            )
            await store.add_task(task)
            return ToolResult(
                output=f"已创建定时任务：\n"
                f"  任务ID：{task.id}\n"
                f"  名称：{task.name}\n"
                f"  时间：{task.cron}（北京时间）\n"
                f"  飞书通知：{'是' if task.notify.feishu else '否'}\n"
                f"  保存文件：{'是' if task.output.save_markdown else '否'}"
            )
        except Exception as exc:
            return ToolResult(output=f"创建任务失败：{exc}", is_error=True)

    return definition, execute


def _create_list_tasks(store: TaskStore) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="list_scheduled_tasks",
        description="List all scheduled tasks with their status",
        category="shell",
        parameters=ToolParameterSchema(properties={}, required=[]),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            tasks = await store.list_tasks()
            if not tasks:
                return ToolResult(output="当前没有定时任务。")
            lines = ["当前定时任务："]
            for i, t in enumerate(tasks, 1):
                status = "✅ 启用" if t.enabled else "⏸ 停用"
                last = ""
                if t.last_run_at:
                    last = f" | 上次执行：{t.last_run_status}"
                lines.append(f"  {i}. [{t.id}] {t.name} | {t.cron} | {status}{last}")
            return ToolResult(output="\n".join(lines))
        except Exception as exc:
            return ToolResult(output=f"查询任务失败：{exc}", is_error=True)

    return definition, execute


def _create_update_task(store: TaskStore) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="update_scheduled_task",
        description="Update an existing scheduled task",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "task_id": {"type": "string", "description": "Task ID to update"},
                "name": {"type": "string", "description": "New task name"},
                "cron": {"type": "string", "description": "New cron expression"},
                "prompt": {"type": "string", "description": "New prompt"},
                "enabled": {"type": "boolean", "description": "Enable or disable the task"},
                "notify_feishu": {"type": "boolean", "description": "Feishu notification toggle"},
                "feishu_title": {"type": "string", "description": "New Feishu title"},
                "save_markdown": {"type": "boolean", "description": "Save output as markdown toggle"},
            },
            required=["task_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            task_id = str(args["task_id"])
            updates: dict[str, Any] = {}
            for key in ("name", "cron", "prompt", "enabled"):
                if key in args and args[key] is not None:
                    updates[key] = args[key]
            task = await store.update_task(task_id, **updates)
            if task is None:
                return ToolResult(output=f"任务 {task_id} 不存在", is_error=True)
            notify_updates: dict[str, Any] = {}
            for key, arg_key in [("feishu", "notify_feishu"), ("feishu_title", "feishu_title")]:
                if arg_key in args and args[arg_key] is not None:
                    notify_updates[key] = args[arg_key]
            if "save_markdown" in args and args["save_markdown"] is not None:
                updated_output = task.output.model_copy(
                    update={"save_markdown": args["save_markdown"]},
                )
                await store.update_task(task_id, output=updated_output)
            if notify_updates:
                updated_notify = task.notify.model_copy(update=notify_updates)
                await store.update_task(task_id, notify=updated_notify)
            task = await store.get_task(task_id)
            return ToolResult(output=f"已更新任务 {task_id}：\n  名称：{task.name}\n  时间：{task.cron}")
        except Exception as exc:
            return ToolResult(output=f"更新任务失败：{exc}", is_error=True)

    return definition, execute


def _create_remove_task(store: TaskStore) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="remove_scheduled_task",
        description="Remove a scheduled task",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "task_id": {"type": "string", "description": "Task ID to remove"},
            },
            required=["task_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            task_id = str(args["task_id"])
            task = await store.get_task(task_id)
            if task is None:
                return ToolResult(output=f"任务 {task_id} 不存在", is_error=True)
            await store.remove_task(task_id)
            return ToolResult(output=f"已删除任务：{task.name}（{task_id}）")
        except Exception as exc:
            return ToolResult(output=f"删除任务失败：{exc}", is_error=True)

    return definition, execute


def _create_run_task_now(
    store: TaskStore,
    executor: TaskExecutor,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="run_task_now",
        description="Immediately execute a scheduled task",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "task_id": {"type": "string", "description": "Task ID to execute"},
            },
            required=["task_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            task_id = str(args["task_id"])
            task = await store.get_task(task_id)
            if task is None:
                return ToolResult(output=f"任务 {task_id} 不存在", is_error=True)
            result = await executor.execute(task)
            await store.update_run_status(task_id, "success", result[:500])
            preview = result[:1000] + ("..." if len(result) > 1000 else "")
            return ToolResult(output=f"任务 {task.name} 执行完成：\n{preview}")
        except Exception as exc:
            return ToolResult(output=f"执行任务失败：{exc}", is_error=True)

    return definition, execute


__all__ = ["create_task_tools"]
