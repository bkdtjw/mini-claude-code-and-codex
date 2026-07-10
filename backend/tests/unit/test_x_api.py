from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes import mcp as mcp_routes
from backend.api.x_search_service import XSearchQuery, XSearchResult
from backend.common.x_budget import XBudgetError
from backend.config.settings import settings
from backend.core.s02_tools.builtin.x_client import XClientConfig, XClientError, XPost
from backend.core.s05_skills import SpecRegistry

_AUTH = {"Authorization": "Bearer test-secret"}


class _FakeMCP:
    # 替换真 MCP 管理器：避免 lifespan 关停时去 DB 列 MCP 服务器（本模块不碰 DB）。
    async def list_servers(self) -> list[object]:
        return []

    async def disconnect_all(self) -> None:
        return None


@pytest.fixture(autouse=True)
def bind_test_database() -> Generator[None, None, None]:
    # 鉴权/路由测试不碰 DB（init_* 已 no-op），跳过 PostgresContainer 消除 teardown flake。
    yield


async def _noop_init_db() -> None:
    return None


async def _noop_init_runtime(**_kwargs: object) -> tuple[SpecRegistry, None]:
    return SpecRegistry(), None


def _noop_init_task_queue(*_args: object, **_kwargs: object) -> None:
    return None


def _prime(monkeypatch: pytest.MonkeyPatch, *, flag: bool) -> None:
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    monkeypatch.setattr(settings, "x_api_enabled", flag)
    monkeypatch.setattr("backend.api.app.init_db", _noop_init_db)
    monkeypatch.setattr("backend.api.app.init_agent_runtime", _noop_init_runtime)
    monkeypatch.setattr("backend.api.app.init_task_queue", _noop_init_task_queue)
    monkeypatch.setattr(mcp_routes, "mcp_server_manager", _FakeMCP())


def _post(likes: int = 12, handle: str = "alice") -> XPost:
    return XPost(
        author_name="Alice", author_handle=handle, text="claude is great",
        likes=likes, retweets=3, replies=1, views=900,
        created_at="2026-01-01", url=f"https://x.com/{handle}/1",
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    _prime(monkeypatch, flag=True)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_search_returns_structured_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(config: XClientConfig, query: XSearchQuery) -> XSearchResult:
        return XSearchResult(posts=[_post()], rate_limited=False, cached=False)

    monkeypatch.setattr("backend.api.routes.x_api.run_x_search", _fake)
    resp = client.get("/api/x/searches?q=claude&days=7&limit=3", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "claude" and body["count"] == 1
    assert body["results"][0]["author_handle"] == "alice"
    assert body["rate_limited"] is False


def test_missing_token_is_401(client: TestClient) -> None:
    assert client.get("/api/x/searches?q=claude").status_code == 401


def test_invalid_days_is_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(config: XClientConfig, query: XSearchQuery) -> XSearchResult:
        return XSearchResult(posts=[])

    monkeypatch.setattr("backend.api.routes.x_api.run_x_search", _fake)
    assert client.get("/api/x/searches?q=claude&days=9999", headers=_AUTH).status_code == 422


def test_empty_query_is_422(client: TestClient) -> None:
    assert client.get("/api/x/searches?q=", headers=_AUTH).status_code == 422


def test_budget_exceeded_is_429_with_retry_after(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(config: XClientConfig, query: XSearchQuery) -> XSearchResult:
        raise XBudgetError("今日额度已用尽", 3600)

    monkeypatch.setattr("backend.api.routes.x_api.run_x_search", _fake)
    resp = client.get("/api/x/searches?q=claude", headers=_AUTH)
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "3600"
    assert resp.json()["detail"]["code"] == "X_BUDGET_EXCEEDED"


def test_upstream_error_is_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(config: XClientConfig, query: XSearchQuery) -> XSearchResult:
        raise XClientError("X/Twitter 登录被 Cloudflare 拦截")

    monkeypatch.setattr("backend.api.routes.x_api.run_x_search", _fake)
    resp = client.get("/api/x/searches?q=claude", headers=_AUTH)
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "X_UPSTREAM_ERROR"


def test_route_absent_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _prime(monkeypatch, flag=False)  # 开关关闭 → 路由根本不注册
    with TestClient(create_app()) as test_client:
        resp = test_client.get("/api/x/searches?q=claude", headers=_AUTH)
        assert resp.status_code == 404


def test_sort_engagement_reorders_results(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(config: XClientConfig, query: XSearchQuery) -> XSearchResult:
        return XSearchResult(posts=[_post(likes=1, handle="low"), _post(likes=100, handle="high")])

    monkeypatch.setattr("backend.api.routes.x_api.run_x_search", _fake)
    resp = client.get("/api/x/searches?q=claude&sort=engagement", headers=_AUTH)
    assert resp.status_code == 200
    assert [r["author_handle"] for r in resp.json()["results"]] == ["high", "low"]


def test_compare_returns_items(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.api.routes.x_api_models import XCompareItem

    async def _fake_compare(config: XClientConfig, words: list[str], days: int, limit: int) -> list[XCompareItem]:
        return [XCompareItem(query=w, count=1, total_engagement=10, weighted_score=5.0) for w in words]

    monkeypatch.setattr("backend.api.routes.x_api.compare_queries", _fake_compare)
    resp = client.get("/api/x/compare?q=claude,gpt&days=7", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7 and [item["query"] for item in body["items"]] == ["claude", "gpt"]


def test_compare_empty_query_is_422(client: TestClient) -> None:
    assert client.get("/api/x/compare?q=%20%2C%20", headers=_AUTH).status_code == 422


class _FakeKnowledgeService:
    def __init__(self, *, kb_exists: bool = True) -> None:
        self._kb_exists = kb_exists

    async def get_kb(self, kb_id: str) -> object | None:
        return {"id": kb_id} if self._kb_exists else None


def _prime_exports(
    monkeypatch: pytest.MonkeyPatch, *, kb_exists: bool = True, posts: list[XPost] | None = None
) -> None:
    from backend.core.s13_knowledge import IngestResult

    async def _fake_search(config: XClientConfig, query: XSearchQuery) -> XSearchResult:
        return XSearchResult(posts=list(posts or []))

    async def _fake_ingest(kb_id: str, query: str, days: int, plist: list[XPost]) -> IngestResult:
        return IngestResult(kb_id=kb_id, document_id="doc-9", status="ready", chunk_count=2)

    monkeypatch.setattr(
        "backend.api.routes.x_api.KnowledgeService", lambda: _FakeKnowledgeService(kb_exists=kb_exists)
    )
    monkeypatch.setattr("backend.api.routes.x_api.run_x_search", _fake_search)
    monkeypatch.setattr("backend.api.routes.x_api.ingest_x_posts", _fake_ingest)


def test_export_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _prime_exports(monkeypatch, posts=[_post()])
    resp = client.post(
        "/api/x/exports", json={"query": "claude", "kb_id": "kb-x"}, headers=_AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc-9" and body["status"] == "ready"
    assert body["post_count"] == 1 and body["chunk_count"] == 2
    assert body["filename"].startswith("x-sentiment-")


def test_export_kb_not_found_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _prime_exports(monkeypatch, kb_exists=False)
    resp = client.post(
        "/api/x/exports", json={"query": "claude", "kb_id": "missing"}, headers=_AUTH
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "X_EXPORT_KB_NOT_FOUND"


def test_export_empty_result_skips_ingest(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _prime_exports(monkeypatch, posts=[])
    resp = client.post(
        "/api/x/exports", json={"query": "nobody-tweets-this", "kb_id": "kb-x"}, headers=_AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "empty" and body["post_count"] == 0 and body["document_id"] == ""


def test_export_limit_over_30_is_422(client: TestClient) -> None:
    resp = client.post(
        "/api/x/exports", json={"query": "claude", "kb_id": "kb-x", "limit": 31}, headers=_AUTH
    )
    assert resp.status_code == 422
