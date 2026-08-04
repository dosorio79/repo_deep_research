"""Contract tests for the minimal M3 FastAPI backend."""

import os
from importlib.metadata import version
from pathlib import Path

import httpx
import pytest
from openai import OpenAIError
from qdrant_client.http.exceptions import ResponseHandlingException

import repo_research.api as api_module
from repo_research.api import create_app
from repo_research.config import Settings
from repo_research.models import (
    ParsedChunk,
    RagMode,
    RagRequest,
    ResearchAnswer,
    ResearchRequest,
    SearchResult,
)
from repo_research.rag import AnswerGenerationResult
from repo_research.research import ResearchAgentResult


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


class FakeResearchAgent:
    """Fake agentic research model for API tests."""

    def run_research(
        self,
        *,
        request: object,
        tools: object,
    ) -> ResearchAgentResult:
        del tools
        if not isinstance(request, ResearchRequest):
            raise AssertionError("expected ResearchRequest")
        return ResearchAgentResult(
            answer=ResearchAnswer(
                question=request.question,
                mode=RagMode.CHANGE,
                summary="Insufficient repository evidence to produce a plan.",
                confidence=0.0,
                insufficient_evidence=True,
            )
        )


class OneResultDatabase(FakeDatabase):
    """Fake database that returns one result so answer generation is reached."""

    def search(self, query: object) -> list[SearchResult]:
        return [
            SearchResult(
                chunk=ParsedChunk(
                    chunk_id="point-1",
                    repository_id="repo",
                    commit_hash="commit",
                    path="src/example.py",
                    language="python",
                    chunk_type="function",
                    symbol="example",
                    start_line=1,
                    end_line=3,
                    content="def example() -> None:\n    pass\n",
                    content_hash="hash",
                ),
                score=0.9,
            )
        ]


class UnavailableDatabase(FakeDatabase):
    """Fake database that mirrors a refused Qdrant connection."""

    def search(self, query: object) -> list[SearchResult]:
        raise ResponseHandlingException(Exception("Connection refused"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_app_uses_package_version() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    assert app.version == version("repo-deep-research")


def test_create_app_loads_env_local_before_runtime_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=local-test-key\n",
        encoding="utf-8",
    )

    create_app(
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    assert os.environ["OPENAI_API_KEY"] == "local-test-key"


@pytest.mark.anyio
async def test_health_reports_qdrant_status() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
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
        research_agent=FakeResearchAgent(),
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
        research_agent=FakeResearchAgent(),
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
        research_agent=FakeResearchAgent(),
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


@pytest.mark.anyio
async def test_research_returns_agentic_trace_shape() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/research",
            json={
                "question": "Which modules change for bounded research?",
                "budget": {
                    "max_searches": 1,
                    "max_file_reads": 1,
                    "max_total_tool_calls": 1,
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["insufficient_evidence"] is True
    assert body["answer"]["mode"] == "change"
    assert body["trace"]["tool_call_count"] == 0


@pytest.mark.anyio
async def test_rag_returns_stable_error_when_openai_client_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_openai_error(settings: Settings) -> FakeGenerator:
        raise OpenAIError("Missing credentials")

    monkeypatch.setattr(api_module, "create_answer_model", raise_openai_error)
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=OneResultDatabase(healthy=True),
        research_agent=FakeResearchAgent(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/rag",
            json={"question": "Where is example logic?", "limit": 5},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "OpenAI client is unavailable; check local credentials and service "
            "configuration."
        )
    }


@pytest.mark.anyio
async def test_rag_returns_stable_error_when_qdrant_is_unavailable() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=UnavailableDatabase(healthy=False),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/rag",
            json={"question": "Where is example logic?", "limit": 5},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Repository vector store is unavailable; start Qdrant and retry the "
            "request."
        )
    }
