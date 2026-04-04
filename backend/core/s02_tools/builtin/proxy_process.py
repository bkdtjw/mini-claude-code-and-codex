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
    """mihomo 进程错误。"""


class MihomoProcess:
    """管理 mihomo 进程的生命周期。"""

    def __init__(self, config: ProxyConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> str:
        """启动 mihomo 并等待 RESTful API 就绪。"""
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
            return "mihomo 启动超时，未能连接 RESTful API"
        except MihomoProcessError as exc:
            await self.stop()
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            await self.stop()
            return f"启动 mihomo 失败: {exc}"

    async def stop(self) -> None:
        """停止 mihomo 进程。"""
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
        """检查进程是否仍在运行。"""
        return self._process is not None and self._process.returncode is None

    async def restart(self) -> str:
        """重启 mihomo。"""
        try:
            await self.stop()
            return await self.start()
        except Exception as exc:  # noqa: BLE001
            return f"重启 mihomo 失败: {exc}"

    def _validate_paths(self) -> None:
        mihomo_path = Path(self._config.mihomo_path)
        config_path = Path(self._config.config_path)
        work_dir = Path(self._config.work_dir)
        if not mihomo_path.is_file():
            raise MihomoProcessError(f"mihomo 可执行文件不存在: {mihomo_path}")
        if not config_path.is_file():
            raise MihomoProcessError(f"mihomo 配置文件不存在: {config_path}")
        if not work_dir.is_dir():
            raise MihomoProcessError(f"mihomo 工作目录不存在: {work_dir}")

    async def _wait_until_ready(self) -> str:
        try:
            api = MihomoAPI(self._config.api_url, self._config.api_secret)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + START_TIMEOUT_SECONDS
            while loop.time() < deadline:
                if self._process is not None and self._process.returncode is not None:
                    stderr_text = await self._read_stderr()
                    raise MihomoProcessError(stderr_text or "mihomo 进程已退出")
                version = await api.get_version()
                if version:
                    return version
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            return ""
        except MihomoProcessError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MihomoProcessError(f"等待 mihomo 就绪失败: {exc}") from exc

    async def _read_stderr(self) -> str:
        try:
            if self._process is None or self._process.stderr is None:
                return ""
            data = await self._process.stderr.read()
            return data.decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            return ""


__all__ = ["MihomoProcess", "MihomoProcessError"]
