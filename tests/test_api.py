"""Contract tests for the minimal M3 FastAPI backend."""

from pathlib import Path

from fastapi.testclient import TestClient

from repo_research.api import create_app
from repo_research.config import Settings
from repo_research.models import ResearchRequest, SearchResult
from repo_research.research import ResearchAnswerDraft


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
        request: ResearchRequest,
        evidence_context: str,
    ) -> ResearchAnswerDraft:
        raise AssertionError("empty retrieval should not call the model")


def test_health_reports_qdrant_status() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "qdrant": True}


def test_research_returns_insufficient_evidence_shape() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
    )
    client = TestClient(app)

    response = client.post(
        "/research",
        json={"question": "Where is missing logic?", "limit": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["evidence"] == []
