"""Contract tests for the minimal M3 FastAPI backend."""

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
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
    AnswerSnapshot,
    EvaluationDashboardSummary,
    EvaluationResultList,
    EvaluationResultSummary,
    EvaluationRunKindAverage,
    EvaluationRunList,
    EvaluationRunStatus,
    EvaluationRunSummary,
    EvaluationSourceType,
    EvidenceItem,
    FeedbackEvent,
    MonitoringRunDetail,
    MonitoringRunList,
    MonitoringRunSummary,
    MonitoringSummary,
    ParsedChunk,
    RagMode,
    RagRequest,
    RagRunTrace,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchRequest,
    RetrievalEvaluationList,
    RetrievalEvaluationSummary,
    RetrievalMode,
    RunKind,
    SearchResult,
)
from repo_research.rag import AnswerGenerationResult
from repo_research.research import ResearchAgentResult


class FakeDatabase:
    """Fake database for API tests."""

    def __init__(self, *, healthy: bool) -> None:
        self._healthy = healthy
        self.replaced_repository_id: str | None = None
        self.replaced_chunks: list[ParsedChunk] = []
        self.existing_chunk_count = 0

    def health_check(self) -> bool:
        return self._healthy

    def search(self, query: object) -> list[SearchResult]:
        return []

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        self.replaced_repository_id = repository_id
        self.replaced_chunks = chunks

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        return self.existing_chunk_count


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
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError("sync research agent ran inside the ASGI event loop")
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


class FakeRecordingStore:
    """Capture monitoring and feedback persistence calls from API routes."""

    def __init__(self) -> None:
        self.runs: list[tuple[RunKind, RagRunTrace]] = []
        self.answer_snapshots: list[AnswerSnapshot] = []
        self.feedback_events: list[FeedbackEvent] = []
        self.summary = MonitoringSummary(total_runs=0)
        self.run_list = MonitoringRunList()
        self.run_detail: MonitoringRunDetail | None = None
        self.evaluation_dashboard_summary = EvaluationDashboardSummary(
            total_runs=0,
            completed_runs=0,
            failed_runs=0,
            total_results=0,
            unsupported_claim_rate=0,
        )
        self.evaluation_run_list = EvaluationRunList()
        self.evaluation_result_list = EvaluationResultList()
        self.retrieval_evaluation_list = RetrievalEvaluationList()

    def record_run(self, *, run_kind: RunKind, trace: RagRunTrace) -> None:
        self.runs.append((run_kind, trace))

    def record_answer_snapshot(self, snapshot: AnswerSnapshot) -> None:
        self.answer_snapshots.append(snapshot)

    def record_feedback(self, event: FeedbackEvent) -> None:
        self.feedback_events.append(event)

    def monitoring_summary(self) -> MonitoringSummary:
        return self.summary

    def list_monitoring_runs(self, **_kwargs: object) -> MonitoringRunList:
        return self.run_list

    def get_monitoring_run(self, request_id: str) -> MonitoringRunDetail | None:
        if self.run_detail and self.run_detail.request_id == request_id:
            return self.run_detail
        return None

    def evaluation_summary(self) -> EvaluationDashboardSummary:
        return self.evaluation_dashboard_summary

    def list_evaluation_runs(self, **_kwargs: object) -> EvaluationRunList:
        return self.evaluation_run_list

    def list_evaluation_results(self, **_kwargs: object) -> EvaluationResultList:
        return self.evaluation_result_list

    def list_retrieval_evaluation_results(self) -> RetrievalEvaluationList:
        return self.retrieval_evaluation_list


def test_record_completed_answer_persists_agentic_snapshot() -> None:
    recording_store = FakeRecordingStore()
    trace = RagRunTrace(
        request_id="request-1",
        session_id="session-1",
        started_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        completed_at=datetime(2026, 8, 10, 12, 0, 1, tzinfo=UTC),
        repository_id="repo-id",
        repository_name="repo",
        branch="main",
        commit_hash="abc123",
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.DENSE,
        retrieval_limit=5,
        retrieved_chunk_count=1,
        unique_file_count=1,
        evidence_ids=["E1"],
        latency_ms_total=1000,
        latency_ms_retrieval=100,
        tool_call_count=2,
    )
    evidence = EvidenceItem(
        evidence_id="E1",
        path="src/repo_research/api.py",
        start_line=1,
        end_line=5,
        symbol="create_app",
        score=0.9,
        reason="Relevant API route.",
    )
    answer = ResearchAnswer(
        question="Which modules change for evaluation persistence?",
        mode=RagMode.CHANGE,
        summary="Persist answer snapshots from API routes.",
        evidence=[evidence],
        confidence=0.8,
    )

    api_module._record_completed_answer(
        recording_store=recording_store,
        run_kind=RunKind.AGENTIC,
        answer=answer,
        trace=trace,
    )

    assert recording_store.runs == [(RunKind.AGENTIC, trace)]
    assert len(recording_store.answer_snapshots) == 1
    snapshot = recording_store.answer_snapshots[0]
    assert snapshot.request_id == "request-1"
    assert snapshot.run_kind is RunKind.AGENTIC
    assert snapshot.answer.summary == "Persist answer snapshots from API routes."
    assert snapshot.evidence[0].path == "src/repo_research/api.py"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _commit_test_repo(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
    )


def _monitoring_run_summary(*, request_id: str) -> MonitoringRunSummary:
    return MonitoringRunSummary(
        request_id=request_id,
        session_id="session-1",
        run_kind=RunKind.DIRECT,
        started_at=datetime(2026, 8, 7, 12, tzinfo=UTC),
        completed_at=datetime(2026, 8, 7, 12, 0, 1, tzinfo=UTC),
        repository_name="repo",
        branch="main",
        commit_hash="abc123",
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.HYBRID,
        retrieved_chunk_count=3,
        unique_file_count=2,
        evidence_count=2,
        latency_ms_total=1000,
        latency_ms_retrieval=200,
        latency_ms_model=800,
        tool_call_count=0,
        insufficient_evidence=False,
        has_error=False,
        feedback_useful=0,
        feedback_not_useful=0,
        total_estimated_cost_usd=None,
    )


def test_app_uses_package_version() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    assert app.version == version("repo-deep-research")


def test_openapi_schema_has_user_facing_metadata() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    schema = app.openapi()

    assert schema["info"]["title"] == "Repo Deep Research"
    assert schema["info"]["version"] == version("repo-deep-research")
    assert {tag["name"] for tag in schema["tags"]} == {
        "system",
        "repositories",
        "answers",
        "feedback",
        "monitoring",
        "evaluations",
    }
    assert schema["paths"]["/rag"]["post"]["operationId"] == "run_direct_rag"
    assert schema["paths"]["/research"]["post"]["tags"] == ["answers"]
    assert schema["paths"]["/evaluations/results"]["get"]["tags"] == ["evaluations"]
    assert schema["paths"]["/evaluations/retrieval"]["get"]["operationId"] == (
        "list_retrieval_evaluation_results"
    )


def test_versioned_openapi_contract_matches_app_schema() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )
    contract_path = Path("docs/api/openapi.json")

    assert contract_path.exists()
    persisted_schema = contract_path.read_text(encoding="utf-8")
    assert json.loads(persisted_schema) == app.openapi()


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
async def test_root_redirects_to_swagger_docs() -> None:
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
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


@pytest.mark.anyio
async def test_swagger_docs_and_openapi_json_are_available() -> None:
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
        docs_response = await client.get("/docs")
        schema_response = await client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert "Swagger UI" in docs_response.text
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert schema["info"]["title"] == "Repo Deep Research"
    assert "/repositories/ingest" in schema["paths"]
    assert "/monitoring/summary" in schema["paths"]


@pytest.mark.anyio
async def test_ingest_repository_indexes_local_repository_path(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text(
        "def answer() -> int:\n    return 42\n",
        encoding="utf-8",
    )
    database = FakeDatabase(healthy=True)
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=database,
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/repositories/ingest",
            json={"repository_address": str(tmp_path)},
        )

    assert response.status_code == 200
    body = response.json()
    repository = RepositoryIdentity.model_validate(body["repository"])
    assert repository.root_path == tmp_path.resolve()
    assert body["indexed_chunks"] >= 1
    assert body["index_updated"] is True
    assert body["skipped_files"] == []
    assert database.replaced_repository_id == repository.repository_id
    assert [chunk.path for chunk in database.replaced_chunks] == ["example.py"]


@pytest.mark.anyio
async def test_ingest_repository_skips_existing_git_revision(tmp_path: Path) -> None:
    (tmp_path / "invalid.py").write_text("def broken(:\n", encoding="utf-8")
    _commit_test_repo(tmp_path)
    database = FakeDatabase(healthy=True)
    database.existing_chunk_count = 7
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=database,
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/repositories/ingest",
            json={"repository_address": str(tmp_path)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["indexed_chunks"] == 7
    assert body["index_updated"] is False
    assert body["skipped_files"] == []
    assert database.replaced_repository_id is None


@pytest.mark.anyio
async def test_ingest_repository_returns_stable_error_for_missing_path(
    tmp_path: Path,
) -> None:
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
            "/repositories/ingest",
            json={"repository_path": str(tmp_path / "missing")},
        )

    assert response.status_code == 400
    assert "repository path is not a directory" in response.json()["detail"]


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
async def test_rag_persists_monitoring_run_with_session_id() -> None:
    recording_store = FakeRecordingStore()
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/rag",
            json={
                "question": "Where is missing logic?",
                "limit": 5,
                "session_id": "browser-session",
            },
        )

    assert response.status_code == 200
    assert response.json()["trace"]["session_id"] == "browser-session"
    assert len(recording_store.runs) == 1
    run_kind, trace = recording_store.runs[0]
    assert run_kind is RunKind.DIRECT
    assert trace.session_id == "browser-session"
    assert trace.request_id == response.json()["trace"]["request_id"]
    assert len(recording_store.answer_snapshots) == 1
    snapshot = recording_store.answer_snapshots[0]
    assert snapshot.request_id == trace.request_id
    assert snapshot.session_id == "browser-session"
    assert snapshot.run_kind is RunKind.DIRECT
    assert snapshot.question == "Where is missing logic?"
    assert snapshot.answer.summary == response.json()["answer"]["summary"]


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
async def test_research_generates_fallback_session_id_for_monitoring() -> None:
    recording_store = FakeRecordingStore()
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/research",
            json={"question": "Which modules change for bounded research?"},
        )

    assert response.status_code == 200
    session_id = response.json()["trace"]["session_id"]
    assert isinstance(session_id, str)
    assert session_id
    assert len(recording_store.runs) == 1
    run_kind, trace = recording_store.runs[0]
    assert run_kind is RunKind.AGENTIC
    assert trace.session_id == session_id
    assert len(recording_store.answer_snapshots) == 1
    snapshot = recording_store.answer_snapshots[0]
    assert snapshot.request_id == trace.request_id
    assert snapshot.session_id == session_id
    assert snapshot.run_kind is RunKind.AGENTIC
    assert snapshot.question == "Which modules change for bounded research?"
    assert snapshot.answer.insufficient_evidence is True


@pytest.mark.anyio
async def test_feedback_persists_user_feedback() -> None:
    recording_store = FakeRecordingStore()
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/feedback",
            json={
                "session_id": "browser-session",
                "request_id": "request-1",
                "run_kind": "direct",
                "useful": True,
                "comment": "Grounded enough.",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "browser-session"
    assert body["request_id"] == "request-1"
    assert body["useful"] is True
    assert len(recording_store.feedback_events) == 1
    assert recording_store.feedback_events[0].comment == "Grounded enough."


@pytest.mark.anyio
async def test_monitoring_summary_returns_recorder_aggregates() -> None:
    recording_store = FakeRecordingStore()
    recording_store.summary = MonitoringSummary(total_runs=3)
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/monitoring/summary")

    assert response.status_code == 200
    assert response.json()["total_runs"] == 3


@pytest.mark.anyio
async def test_monitoring_runs_returns_recorder_history() -> None:
    recording_store = FakeRecordingStore()
    recording_store.run_list = MonitoringRunList(
        runs=[_monitoring_run_summary(request_id="request-1")]
    )
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/monitoring/runs",
            params={"limit": 25, "run_kind": "direct", "feedback": "none"},
        )

    assert response.status_code == 200
    assert response.json()["runs"][0]["request_id"] == "request-1"


@pytest.mark.anyio
async def test_monitoring_run_detail_returns_recorder_detail() -> None:
    recording_store = FakeRecordingStore()
    recording_store.run_detail = MonitoringRunDetail(
        **_monitoring_run_summary(request_id="request-1").model_dump(),
        repository_id="repo-id",
        retrieval_limit=5,
        error_type=None,
        error_message=None,
        model_usage=[],
        feedback_events=[],
    )
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/monitoring/runs/request-1")

    assert response.status_code == 200
    assert response.json()["repository_id"] == "repo-id"


@pytest.mark.anyio
async def test_monitoring_run_detail_returns_404_for_missing_run() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=FakeRecordingStore(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/monitoring/runs/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "monitoring run not found"}


@pytest.mark.anyio
async def test_evaluation_summary_returns_recorder_aggregates() -> None:
    recording_store = FakeRecordingStore()
    recording_store.evaluation_dashboard_summary = EvaluationDashboardSummary(
        total_runs=2,
        completed_runs=1,
        failed_runs=1,
        total_results=3,
        average_score=4.2,
        unsupported_claim_rate=0.33,
        average_by_run_kind=[
            EvaluationRunKindAverage(
                run_kind=RunKind.AGENTIC,
                average_score=4.5,
                result_count=2,
                unsupported_claim_count=1,
            )
        ],
    )
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/evaluations/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] == 2
    assert body["average_by_run_kind"][0]["run_kind"] == "agentic"


@pytest.mark.anyio
async def test_evaluation_runs_returns_recorder_history() -> None:
    recording_store = FakeRecordingStore()
    recording_store.evaluation_run_list = EvaluationRunList(
        runs=[
            EvaluationRunSummary(
                evaluation_run_id="eval-run-1",
                source_type=EvaluationSourceType.MONITORED_RUNS,
                source_label="monitored-runs",
                context_labels=["repo_deep_research"],
                judge_model="gpt-5.1",
                status=EvaluationRunStatus.COMPLETED,
                started_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
                completed_at=datetime(2026, 8, 11, 12, 1, tzinfo=UTC),
                result_count=2,
                average_score=4.5,
                unsupported_claim_count=1,
            )
        ]
    )
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/evaluations/runs",
            params={"limit": 10, "source_type": "monitored_runs"},
        )

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["evaluation_run_id"] == "eval-run-1"
    assert run["context_labels"] == ["repo_deep_research"]


@pytest.mark.anyio
async def test_evaluation_results_returns_recorder_rows() -> None:
    recording_store = FakeRecordingStore()
    recording_store.evaluation_result_list = EvaluationResultList(
        results=[
            EvaluationResultSummary(
                result_id="result-1",
                evaluation_run_id="eval-run-1",
                source_type=EvaluationSourceType.MONITORED_RUNS,
                source_label="monitored-runs",
                context_label="repo_deep_research",
                repository_name="repo_deep_research",
                branch="dev",
                commit_hash="abc123",
                request_id="request-1",
                run_kind=RunKind.DIRECT,
                question="Where is target?",
                answer_correctness=None,
                faithfulness=5,
                citation_precision=5,
                reference_coverage=None,
                answer_relevance=4,
                presentation_quality=4,
                average_score=4.4,
                unsupported_claim_count=0,
                feedback_useful=1,
                feedback_not_useful=0,
                latency_ms_total=1000,
                total_estimated_cost_usd=None,
                created_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
            )
        ]
    )
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/evaluations/results",
            params={"limit": 10, "run_kind": "direct"},
        )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["result_id"] == "result-1"
    assert result["context_label"] == "repo_deep_research"
    assert result["repository_name"] == "repo_deep_research"


@pytest.mark.anyio
async def test_retrieval_evaluation_results_returns_recorder_rows() -> None:
    recording_store = FakeRecordingStore()
    recording_store.retrieval_evaluation_list = RetrievalEvaluationList(
        results=[
            RetrievalEvaluationSummary(
                dataset="Held-out",
                mode=RetrievalMode.DENSE,
                source_label="eval/held_out.json local alpha smoke",
                limit=5,
                record_count=15,
                file_hit_rate=0.467,
                file_mrr=0.313,
                file_recall=0.311,
                file_precision=0.2,
                symbol_hit_rate=0.4,
                selected=True,
                measured_at=datetime(2026, 8, 13, tzinfo=UTC),
            )
        ]
    )
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=FakeDatabase(healthy=True),
        generator=FakeGenerator(),
        research_agent=FakeResearchAgent(),
        recording_store=recording_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/evaluations/retrieval")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["dataset"] == "Held-out"
    assert result["mode"] == "dense"
    assert result["selected"] is True
    assert result["file_hit_rate"] == 0.467


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


@pytest.mark.anyio
async def test_research_returns_stable_error_when_openai_client_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_openai_error(settings: Settings) -> FakeResearchAgent:
        raise OpenAIError("Missing credentials")

    monkeypatch.setattr(api_module, "create_research_agent", raise_openai_error)
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=OneResultDatabase(healthy=True),
        generator=FakeGenerator(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/research",
            json={"question": "Where is example logic?"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "OpenAI client is unavailable; check local credentials and service "
            "configuration."
        )
    }


@pytest.mark.anyio
async def test_research_returns_stable_error_when_qdrant_is_unavailable() -> None:
    app = create_app(
        settings=Settings(repository_root=Path(".")),
        database=UnavailableDatabase(healthy=False),
        generator=FakeGenerator(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/research",
            json={"question": "Where is example logic?"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "Repository vector store is unavailable; start Qdrant and retry the "
            "request."
        )
    }
