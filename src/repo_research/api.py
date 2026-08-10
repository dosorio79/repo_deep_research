"""Minimal FastAPI backend for M3 grounded direct RAG."""

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAIError
from qdrant_client.http.exceptions import ResponseHandlingException

from repo_research.config import Settings, load_dotenv_environment
from repo_research.ingestion import (
    discover_repository,
    ingest_repository_if_needed,
    materialize_repository_address,
)
from repo_research.models import (
    AnswerSnapshot,
    FeedbackEvent,
    FeedbackRequest,
    IngestSummary,
    MonitoringFeedbackFilter,
    MonitoringRunDetail,
    MonitoringRunList,
    MonitoringSummary,
    ParsedChunk,
    RagAnswer,
    RagRequest,
    RagRunResult,
    RagRunTrace,
    RepositoryIngestRequest,
    ResearchAnswer,
    ResearchRequest,
    ResearchRunResult,
    RunKind,
    SearchQuery,
    SearchResult,
)
from repo_research.monitoring import instrument_fastapi
from repo_research.rag import AnswerGenerator
from repo_research.research import ResearchAgentRunner
from repo_research.runtime import (
    create_answer_model,
    create_bounded_research_service,
    create_database,
    create_direct_rag_service,
    create_recording_store,
    create_research_agent,
)


class RagDatabase(Protocol):
    """Database behavior required by the API routes."""

    def health_check(self) -> bool:
        """Return dependency health."""

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return repository search results."""

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        """Replace current indexed chunks for one repository identity."""

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        """Return indexed chunk count for one repository revision."""


class RecordingStore(Protocol):
    """Monitoring and feedback persistence behavior required by API routes."""

    def record_run(self, *, run_kind: RunKind, trace: RagRunTrace) -> None:
        """Persist one completed run trace."""

    def record_feedback(self, event: FeedbackEvent) -> None:
        """Persist one feedback event."""

    def record_answer_snapshot(self, snapshot: AnswerSnapshot) -> None:
        """Persist one completed answer for later evaluation."""

    def monitoring_summary(self) -> MonitoringSummary:
        """Return aggregate monitoring panels."""

    def list_monitoring_runs(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        has_error: bool | None = None,
        feedback: MonitoringFeedbackFilter = MonitoringFeedbackFilter.ALL,
    ) -> MonitoringRunList:
        """Return recent persisted monitoring runs."""

    def get_monitoring_run(self, request_id: str) -> MonitoringRunDetail | None:
        """Return one persisted monitoring run detail when available."""


def package_version() -> str:
    """Return the installed package version used by FastAPI metadata."""
    try:
        return version("repo-deep-research")
    except PackageNotFoundError:
        return "0.0.0"


def create_app(
    *,
    settings: Settings | None = None,
    database: RagDatabase | None = None,
    generator: AnswerGenerator | None = None,
    research_agent: ResearchAgentRunner | None = None,
    recording_store: RecordingStore | None = None,
) -> FastAPI:
    """Create a FastAPI app with injectable runtime dependencies."""
    load_dotenv_environment(keys=("OPENAI_API_KEY", "OPENAI_ADMIN_KEY"))
    app_settings = settings or Settings()
    app = FastAPI(title="Repo Deep Research", version=package_version())
    instrument_fastapi(app, app_settings)
    if app_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_allowed_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["content-type"],
        )

    def get_database() -> RagDatabase:
        return database or create_database(app_settings)

    def get_generator() -> AnswerGenerator:
        return generator or create_answer_model(app_settings)

    def get_research_agent() -> ResearchAgentRunner:
        return research_agent or create_research_agent(app_settings)

    recording_store_instance = recording_store

    def get_recording_store() -> RecordingStore:
        nonlocal recording_store_instance
        if recording_store_instance is None:
            recording_store_instance = create_recording_store(app_settings)
        return recording_store_instance

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "Repo Deep Research API",
            "health": "/health",
            "ingest": "POST /repositories/ingest",
            "direct_rag": "POST /rag",
            "agentic_rag": "POST /research",
        }

    @app.get("/health")
    async def health() -> dict[str, str | bool]:
        qdrant_ok = False
        try:
            qdrant_ok = get_database().health_check()
        except Exception:
            qdrant_ok = False
        return {"status": "ok" if qdrant_ok else "degraded", "qdrant": qdrant_ok}

    @app.post("/repositories/ingest", response_model=IngestSummary)
    async def ingest_repository(request: RepositoryIngestRequest) -> IngestSummary:
        try:
            root_path = materialize_repository_address(
                request.repository_address,
                app_settings.repository_cache_dir,
            )
            repository, files = discover_repository(
                root_path, app_settings.max_file_size_bytes
            )
            return ingest_repository_if_needed(
                database=get_database(),
                repository=repository,
                files=files,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ResponseHandlingException as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Repository vector store is unavailable; start Qdrant and "
                    "retry ingestion."
                ),
            ) from error

    @app.post("/rag", response_model=RagRunResult)
    async def rag(request: RagRequest) -> RagRunResult:
        root_path = (request.repository_path or app_settings.repository_root).resolve()
        try:
            repository, _ = discover_repository(
                root_path, app_settings.max_file_size_bytes
            )
            service = create_direct_rag_service(
                settings=app_settings,
                database=get_database(),
                generator=get_generator(),
            )
            result = service.run(
                repository=repository,
                request=request.model_copy(update={"repository_path": root_path}),
            )
            _record_completed_answer(
                recording_store=get_recording_store(),
                run_kind=RunKind.DIRECT,
                answer=result.answer,
                trace=result.trace,
            )
            return result
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ResponseHandlingException as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Repository vector store is unavailable; start Qdrant and "
                    "retry the request."
                ),
            ) from error
        except OpenAIError as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OpenAI client is unavailable; check local credentials and "
                    "service configuration."
                ),
            ) from error

    @app.post("/research", response_model=ResearchRunResult)
    async def research(request: ResearchRequest) -> JSONResponse:
        root_path = (request.repository_path or app_settings.repository_root).resolve()
        try:
            repository, _ = discover_repository(
                root_path, app_settings.max_file_size_bytes
            )
            service = create_bounded_research_service(
                settings=app_settings,
                database=get_database(),
                agent=get_research_agent(),
            )
            research_request = request.model_copy(update={"repository_path": root_path})
            result = await service.run_async(
                repository=repository,
                request=research_request,
            )
            _record_completed_answer(
                recording_store=get_recording_store(),
                run_kind=RunKind.AGENTIC,
                answer=result.answer,
                trace=result.trace,
            )
            return JSONResponse(content=jsonable_encoder(result))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ResponseHandlingException as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Repository vector store is unavailable; start Qdrant and "
                    "retry the request."
                ),
            ) from error
        except OpenAIError as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OpenAI client is unavailable; check local credentials and "
                    "service configuration."
                ),
            ) from error

    @app.post("/feedback", response_model=FeedbackEvent)
    async def feedback(request: FeedbackRequest) -> FeedbackEvent:
        event = FeedbackEvent(
            session_id=request.session_id or uuid4().hex,
            request_id=request.request_id,
            run_kind=request.run_kind,
            useful=request.useful,
            comment=request.comment,
            submitted_at=datetime.now(UTC),
        )
        get_recording_store().record_feedback(event)
        return event

    @app.get("/monitoring/summary", response_model=MonitoringSummary)
    async def monitoring_summary() -> MonitoringSummary:
        return get_recording_store().monitoring_summary()

    @app.get("/monitoring/runs", response_model=MonitoringRunList)
    async def monitoring_runs(
        limit: int = Query(default=50, ge=1, le=100),
        run_kind: RunKind | None = None,
        repository_name: str | None = Query(default=None, min_length=1),
        has_error: bool | None = None,
        feedback: MonitoringFeedbackFilter = MonitoringFeedbackFilter.ALL,
    ) -> MonitoringRunList:
        return get_recording_store().list_monitoring_runs(
            limit=limit,
            run_kind=run_kind,
            repository_name=repository_name,
            has_error=has_error,
            feedback=feedback,
        )

    @app.get("/monitoring/runs/{request_id}", response_model=MonitoringRunDetail)
    async def monitoring_run_detail(request_id: str) -> MonitoringRunDetail:
        detail = get_recording_store().get_monitoring_run(request_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="monitoring run not found")
        return detail

    return app


def _record_completed_answer(
    *,
    recording_store: RecordingStore,
    run_kind: RunKind,
    answer: RagAnswer | ResearchAnswer,
    trace: RagRunTrace,
) -> None:
    """Persist monitoring metadata and the answer snapshot used by evaluation."""
    recording_store.record_run(run_kind=run_kind, trace=trace)
    recording_store.record_answer_snapshot(
        AnswerSnapshot(
            request_id=trace.request_id,
            session_id=trace.session_id,
            run_kind=run_kind,
            question=answer.question,
            answer=answer,
            evidence=answer.evidence,
            repository_id=trace.repository_id,
            repository_name=trace.repository_name,
            branch=trace.branch,
            commit_hash=trace.commit_hash,
            question_mode=trace.question_mode,
            retrieval_mode=trace.retrieval_mode,
            retrieval_limit=trace.retrieval_limit,
            created_at=trace.completed_at,
        )
    )


app = create_app()
