from __future__ import annotations

import asyncio
import sys
from typing import Sequence

from backend.cli_support import CliError, CliPrinter, create_session, parse_args, run_repl
from backend.common.errors import AgentError, LLMError


async def main(argv: Sequence[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        printer = CliPrinter()
        session = await create_session(args, event_handler=printer.handle_event)
        await run_repl(session, printer)
    except (CliError, AgentError, LLMError):
        raise
    except Exception as exc:
        raise CliError("CLI_MAIN_ERROR", str(exc)) from exc


def cli_entry() -> None:
    try:
        asyncio.run(main())
    except (CliError, AgentError, LLMError) as exc:
        message = getattr(exc, "message", str(exc))
        print(f"[error] {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
