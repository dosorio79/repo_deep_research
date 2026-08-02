"""Contract tests for the minimal M3 FastAPI backend."""

from pathlib import Path

import httpx
import pytest

from repo_research.api import create_app
from repo_research.config import Settings
from repo_research.models import RagRequest, SearchResult
from repo_research.rag import RagAnswerDraft


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
    ) -> RagAnswerDraft:
        raise AssertionError("empty retrieval should not call the model")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
    assert body["insufficient_evidence"] is True
    assert body["evidence"] == []
