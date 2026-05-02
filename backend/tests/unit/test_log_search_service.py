from __future__ import annotations

import pytest

import backend.common.log_search.service as service
from backend.common.log_search.models import LogSearchQuery, LogSearchSourceError
from backend.schemas.observability import LogEntryResponse


class FakeFileLogSource:
    async def search(self, query: LogSearchQuery) -> list[LogEntryResponse]:
        return [
            LogEntryResponse(
                timestamp="2026-04-30T10:00:00Z",
                level="info",
                event=query.event or "file_event",
                component="file",
            )
        ]


class FakeLokiLogSource:
    def __init__(self, _config: object) -> None:
        return

    async def search(self, query: LogSearchQuery) -> list[LogEntryResponse]:
        return [
            LogEntryResponse(
                timestamp="2026-04-30T10:00:00Z",
                level="info",
                event=query.event or "loki_event",
                component="loki",
            )
        ]


class FailingLokiLogSource:
    def __init__(self, _config: object) -> None:
        return

    async def search(self, _query: LogSearchQuery) -> list[LogEntryResponse]:
        raise LogSearchSourceError("LOKI_DOWN", "loki unavailable")


@pytest.mark.asyncio
async def test_search_logs_uses_file_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.settings, "log_search_backend", "file")
    monkeypatch.setattr(service, "FileLogSource", FakeFileLogSource)

    entries = await service.search_logs(LogSearchQuery(event="target"))

    assert entries[0].component == "file"
    assert entries[0].event == "target"


@pytest.mark.asyncio
async def test_search_logs_uses_loki_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.settings, "log_search_backend", "loki")
    monkeypatch.setattr(service, "LokiLogSource", FakeLokiLogSource)

    entries = await service.search_logs(LogSearchQuery(event="target"))

    assert entries[0].component == "loki"
    assert entries[0].event == "target"


@pytest.mark.asyncio
async def test_loki_backend_falls_back_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.settings, "log_search_backend", "loki")
    monkeypatch.setattr(service.settings, "log_search_fallback", "file")
    monkeypatch.setattr(service, "LokiLogSource", FailingLokiLogSource)
    monkeypatch.setattr(service, "FileLogSource", FakeFileLogSource)

    entries = await service.search_logs(LogSearchQuery(event="target"))

    assert entries[0].component == "file"


@pytest.mark.asyncio
async def test_loki_backend_can_disable_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.settings, "log_search_backend", "loki")
    monkeypatch.setattr(service.settings, "log_search_fallback", "none")
    monkeypatch.setattr(service, "LokiLogSource", FailingLokiLogSource)

    with pytest.raises(LogSearchSourceError, match="LOKI_DOWN"):
        await service.search_logs(LogSearchQuery(event="target"))
