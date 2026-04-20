from __future__ import annotations

import asyncio
import sys
from typing import Sequence

from backend.cli_support import CliError, CliPrinter, create_session, parse_args, run_repl
from backend.common.errors import AgentError, LLMError
from backend.config import close_redis


async def main(argv: Sequence[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        printer = CliPrinter()
        session = await create_session(args, event_handler=printer.handle_event)
        if args.command == "run":
            if session.agent_runtime is None:
                raise CliError("CLI_RUNTIME_MISSING", "Agent runtime is not initialized.")
            loop = await session.agent_runtime.create_loop_from_id(
                args.spec_id,
                workspace=session.state.workspace,
                model=args.model or "",
                provider=args.provider or "",
                task_queue=session.task_queue,
                event_handler=printer.handle_event,
            )
            loop.on(printer.handle_event)
            await loop.run(args.input_text)
            return
        await run_repl(session, printer)
    except (CliError, AgentError, LLMError):
        raise
    except Exception as exc:
        raise CliError("CLI_MAIN_ERROR", str(exc)) from exc
    finally:
        await close_redis()


def cli_entry() -> None:
    try:
        asyncio.run(main())
    except (CliError, AgentError, LLMError) as exc:
        message = getattr(exc, "message", str(exc))
        print(f"[error] {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
