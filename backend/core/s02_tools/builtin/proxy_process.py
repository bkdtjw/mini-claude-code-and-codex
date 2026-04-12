from __future__ import annotations

import asyncio
from asyncio.subprocess import PIPE
from pathlib import Path

from .proxy_api import MihomoAPI
from .proxy_models import ProxyConfig

POLL_INTERVAL_SECONDS = 0.5
START_TIMEOUT_SECONDS = 5.0
STOP_TIMEOUT_SECONDS = 5.0


class MihomoProcessError(Exception):
    """Raised when mihomo process operations fail."""


class MihomoProcess:
    """Manage the mihomo process lifecycle."""

    def __init__(self, config: ProxyConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> str:
        try:
            self._validate_paths()
            if self.is_running:
                await self.stop()
            self._process = await asyncio.create_subprocess_exec(
                self._config.mihomo_path,
                "-d",
                self._config.work_dir,
                "-f",
                self._config.config_path,
                cwd=self._config.work_dir,
                stdout=PIPE,
                stderr=PIPE,
            )
            version = await self._wait_until_ready()
            if version:
                return version
            await self.stop()
            return "mihomo startup timed out before the RESTful API became ready"
        except MihomoProcessError as exc:
            await self.stop()
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            await self.stop()
            return f"Failed to start mihomo: {exc}"

    async def stop(self) -> None:
        try:
            if self._process is None:
                return
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=STOP_TIMEOUT_SECONDS)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        except ProcessLookupError:
            return
        except Exception:  # noqa: BLE001
            return
        finally:
            self._process = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def restart(self) -> str:
        try:
            await self.stop()
            return await self.start()
        except Exception as exc:  # noqa: BLE001
            return f"Failed to restart mihomo: {exc}"

    def _validate_paths(self) -> None:
        mihomo_path = Path(self._config.mihomo_path)
        config_path = Path(self._config.config_path)
        work_dir = Path(self._config.work_dir)
        if not mihomo_path.is_file():
            raise MihomoProcessError(f"mihomo executable not found: {mihomo_path}")
        if not config_path.is_file():
            raise MihomoProcessError(f"mihomo config not found: {config_path}")
        if not work_dir.is_dir():
            raise MihomoProcessError(f"mihomo work directory not found: {work_dir}")

    async def _wait_until_ready(self) -> str:
        try:
            api = MihomoAPI(self._config.api_url, self._config.api_secret)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + START_TIMEOUT_SECONDS
            while loop.time() < deadline:
                if self._process is not None and self._process.returncode is not None:
                    stderr_text = await self._read_stderr()
                    raise MihomoProcessError(stderr_text or "mihomo process exited")
                version = await api.get_version()
                if version:
                    return version
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            return ""
        except MihomoProcessError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MihomoProcessError(f"Failed while waiting for mihomo readiness: {exc}") from exc

    async def _read_stderr(self) -> str:
        try:
            if self._process is None or self._process.stderr is None:
                return ""
            data = await self._process.stderr.read()
            return data.decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            return ""


__all__ = ["MihomoProcess", "MihomoProcessError"]
