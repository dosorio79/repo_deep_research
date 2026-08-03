"""Contract tests for the minimal M3 FastAPI backend."""

from importlib.metadata import version
from pathlib import Path

import httpx
import pytest

from repo_research.api import create_app
from repo_research.config import Settings
from repo_research.models import RagRequest, SearchResult
from repo_research.rag import AnswerGenerationResult


class FakeDatabase:
    """Fake database for API tests."""

    def __init__(self, *, healthy: bool) -> None:
        self._healthy = healthy

    def health_check(self) -> bool:
        return self._healthy

    def search(self, query: object) -> list[SearchResult]:
        return []


class FakeGenerator:
    """Fake model that should not be called for empty retrieval results."""

    def generate_answer(
        self,
        *,
        request: RagRequest,
        evidence_context: str,
    ) -> AnswerGenerationResult:
        raise AssertionError("empty retrieval should not call the model")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_app_uses_package_version() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )

    assert app.version == version("repo-deep-research")


@pytest.mark.anyio
async def test_health_reports_qdrant_status() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "qdrant": True}


@pytest.mark.anyio
async def test_rag_allows_configured_frontend_origin() -> None:
    app = create_app(
        settings=Settings(
            repository_root=Path("."),
            cors_allowed_origins=["http://localhost:5173"],
        ),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.options(
            "/rag",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.anyio
async def test_rag_does_not_allow_frontend_origin_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.options(
            "/rag",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.anyio
async def test_rag_returns_insufficient_evidence_shape() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/rag",
            json={"question": "Where is missing logic?", "limit": 5},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["insufficient_evidence"] is True
    assert body["answer"]["evidence"] == []
    assert body["trace"]["retrieved_chunk_count"] == 0
    assert body["trace"]["tool_call_count"] == 0
