from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


class CmdSpawnTestError(Exception):
    pass


@dataclass
class CheckResult:
    label: str
    ok: bool
    returncode: int | None = None
    error: str = ""
    stdout_preview: str = ""
    stderr_preview: str = ""


def _decode(data: bytes | None) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _preview(text: str, max_chars: int = 400) -> str:
    compact = text.strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}..."


def _build_command() -> list[str]:
    return ["cmd.exe", "/c", "chcp 65001 >nul && cd && dir"]


def run_sync_check(workspace: str) -> CheckResult:
    try:
        completed = subprocess.run(
            _build_command(),
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        stdout = _decode(completed.stdout)
        stderr = _decode(completed.stderr)
        return CheckResult(
            label="subprocess.run",
            ok=completed.returncode == 0,
            returncode=completed.returncode,
            stdout_preview=_preview(stdout),
            stderr_preview=_preview(stderr),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(label="subprocess.run", ok=False, error=f"{type(exc).__name__}: {exc}")


async def run_async_check(workspace: str, use_create_no_window: bool) -> CheckResult:
    label = "asyncio.create_subprocess_exec"
    if use_create_no_window:
        label = f"{label} + CREATE_NO_WINDOW"
    try:
        kwargs: dict[str, object] = {
            "cwd": workspace,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if use_create_no_window and sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = await asyncio.create_subprocess_exec(*_build_command(), **kwargs)
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=10)
        stdout = _decode(stdout_bytes)
        stderr = _decode(stderr_bytes)
        return CheckResult(
            label=label,
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            stdout_preview=_preview(stdout),
            stderr_preview=_preview(stderr),
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(label=label, ok=False, error=f"{type(exc).__name__}: {exc}")


async def main() -> int:
    try:
        workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
        if not workspace.exists():
            raise CmdSpawnTestError(f"Workspace does not exist: {workspace}")
        if not workspace.is_dir():
            raise CmdSpawnTestError(f"Workspace is not a directory: {workspace}")

        results = [run_sync_check(str(workspace)), await run_async_check(str(workspace), use_create_no_window=False)]
        if sys.platform == "win32":
            results.append(await run_async_check(str(workspace), use_create_no_window=True))

        payload = {
            "workspace": str(workspace),
            "python": sys.executable,
            "platform": sys.platform,
            "results": [asdict(item) for item in results],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0 if any(item.ok for item in results) else 1
    except CmdSpawnTestError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
