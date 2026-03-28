from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from backend.common.errors import AgentError, LLMError

from .display import CliPrinter
from .models import CliArgs, CliCommand, CliCommandResult, CliError, CliSession, SessionUpdate
from .session import rebuild_session, run_request

HELP_TEXT = "\n".join(
    [
        "可用命令：",
        "  /help                 显示此帮助",
        "  /clear                清空对话历史",
        "  /model <name>         切换模型",
        "  /workspace <path>     切换工作目录",
        "  /tools                显示当前工具列表",
        "  /exit                 退出",
    ]
)


def parse_args(argv: Sequence[str] | None = None) -> CliArgs:
    parser = argparse.ArgumentParser(prog="miniclaude", description="Agent Studio CLI")
    parser.add_argument("-w", "--workspace", default=os.getcwd(), help="workspace path")
    parser.add_argument("-m", "--model", default=None, help="model name")
    parser.add_argument("-p", "--provider", default=None, help="provider id or name")
    parser.add_argument("--mcp-config", default=None, help="path to MCP server config")
    parser.add_argument(
        "--permission-mode",
        choices=["readonly", "auto", "full"],
        default="auto",
        help="tool permission mode",
    )
    namespace = parser.parse_args(list(argv) if argv is not None else None)
    return CliArgs(
        workspace=os.path.abspath(namespace.workspace),
        model=namespace.model,
        provider=namespace.provider,
        permission_mode=namespace.permission_mode,
        mcp_config=os.path.abspath(namespace.mcp_config) if namespace.mcp_config else None,
    )


def parse_command(raw_command: str) -> CliCommand:
    stripped = raw_command.strip()
    parts = stripped.split(maxsplit=1)
    return CliCommand(name=parts[0].lower(), argument=parts[1].strip() if len(parts) > 1 else "")


def _normalize_value(value: str) -> str:
    return value.strip().strip("\"'")


def _read_multiline_input(printer: CliPrinter) -> str | None:
    lines: list[str] = []
    while True:
        try:
            line = input(printer.prompt(multiline=bool(lines)))
        except EOFError:
            return None
        except KeyboardInterrupt:
            print("\n[input] 已取消当前输入。")
            return ""
        if not lines and not line.strip():
            return ""
        if line == "":
            return "\n".join(lines).strip()
        lines.append(line)


async def handle_command(
    session: CliSession,
    command: CliCommand,
    printer: CliPrinter,
) -> CliCommandResult:
    try:
        if command.name in {"/exit", "/quit"}:
            printer.print_info("bye.")
            return CliCommandResult(session=session, should_exit=True)
        if command.name == "/help":
            printer.print_info(HELP_TEXT)
            return CliCommandResult(session=session)
        if command.name == "/tools":
            printer.print_tools(session)
            return CliCommandResult(session=session)
        if command.name == "/clear":
            session.loop.reset()
            printer.print_info("[info] 对话历史已清空。")
            return CliCommandResult(session=session)
        if command.name == "/model":
            if not command.argument:
                printer.print_info(f"[info] 当前模型: {session.state.model}")
                return CliCommandResult(session=session)
            updated = await rebuild_session(session, SessionUpdate(model=command.argument))
            printer.print_info(f"[info] 已切换到模型 {updated.state.model}，历史已清空。")
            return CliCommandResult(session=updated)
        if command.name == "/workspace":
            if not command.argument:
                printer.print_info(f"[info] 当前工作目录: {session.state.workspace}")
                return CliCommandResult(session=session)
            updated = await rebuild_session(
                session,
                SessionUpdate(workspace=_normalize_value(command.argument)),
            )
            printer.print_info(f"[info] 已切换工作目录到 {updated.state.workspace}，历史已清空。")
            return CliCommandResult(session=updated)
        printer.print_info("[error] 未知命令，输入 /help 查看可用命令。")
        return CliCommandResult(session=session)
    except (CliError, AgentError, LLMError):
        raise
    except Exception as exc:
        raise CliError("CLI_COMMAND_ERROR", str(exc)) from exc


async def run_repl(session: CliSession, printer: CliPrinter) -> None:
    try:
        current_session = session
        printer.print_welcome(current_session)
        while True:
            user_input = _read_multiline_input(printer)
            if user_input is None:
                printer.print_info("bye.")
                return
            if not user_input:
                continue
            if user_input.startswith("/"):
                result = await handle_command(current_session, parse_command(user_input), printer)
                current_session = result.session
                if result.should_exit:
                    return
                continue
            try:
                await run_request(current_session, user_input)
            except CliError as exc:
                printer.print_info(f"[error] {exc.message}")
            except (AgentError, LLMError):
                continue
    except (CliError, AgentError, LLMError):
        raise
    except Exception as exc:
        raise CliError("CLI_REPL_ERROR", str(exc)) from exc


__all__ = ["handle_command", "parse_args", "parse_command", "run_repl"]
