"""FastAPI backend for Repo Deep Research."""

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from openai import OpenAIError
from qdrant_client.http.exceptions import ResponseHandlingException
from starlette.concurrency import run_in_threadpool

from repo_research.config import Settings, load_dotenv_environment
from repo_research.graph_models import GraphSummary
from repo_research.ingestion import (
    discover_repository,
    ingest_repository_if_needed,
    materialize_repository_address,
)
from repo_research.models import (
    AnswerSnapshot,
    EvaluationDashboardSummary,
    EvaluationResultList,
    EvaluationRunList,
    EvaluationRunStatus,
    EvaluationSourceType,
    FeedbackEvent,
    FeedbackRequest,
    GroundTruthEvaluationList,
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
    RetrievalEvaluationList,
    RunKind,
    SearchQuery,
    SearchResult,
    VersionProvenance,
)
from repo_research.monitoring import instrument_fastapi
from repo_research.protocols import RepositoryGraphStore
from repo_research.rag import AnswerGenerator
from repo_research.research import ResearchAgentRunner
from repo_research.runtime import (
    create_answer_model,
    create_bounded_research_service,
    create_database,
    create_direct_rag_service,
    create_graph_store,
    create_recording_store,
    create_research_agent,
)
from repo_research.versioning import current_app_version_info

OPENAPI_TAGS = [
    {
        "name": "system",
        "description": "API discovery and dependency health.",
    },
    {
        "name": "repositories",
        "description": "Repository ingestion and indexing.",
    },
    {
        "name": "answers",
        "description": "Direct RAG and bounded agentic research answers.",
    },
    {
        "name": "feedback",
        "description": "Useful/not-useful feedback linked to answer runs.",
    },
    {
        "name": "monitoring",
        "description": "Persisted run monitoring summaries and details.",
    },
    {
        "name": "evaluations",
        "description": "Persisted answer-evaluation summaries and results.",
    },
]


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

    def get_chunks(
        self, repository_id: str, commit_hash: str, chunk_ids: list[str]
    ) -> list[ParsedChunk]:
        """Return canonical chunks for one repository revision."""


class RecordingStore(Protocol):
    """Monitoring and feedback persistence behavior required by API routes."""

    def record_run(self, *, run_kind: RunKind, trace: RagRunTrace) -> None:
        """Persist one completed run trace."""

    def record_feedback(self, event: FeedbackEvent) -> FeedbackEvent:
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

    def evaluation_summary(self) -> EvaluationDashboardSummary:
        """Return aggregate answer-evaluation panels."""

    def list_evaluation_runs(
        self,
        *,
        limit: int = 50,
        source_type: EvaluationSourceType | None = None,
        status: EvaluationRunStatus | None = None,
    ) -> EvaluationRunList:
        """Return recent persisted evaluation batches."""

    def list_evaluation_results(
        self,
        *,
        limit: int = 50,
        source_type: EvaluationSourceType | None = None,
        run_kind: RunKind | None = None,
        context_label: str | None = None,
    ) -> EvaluationResultList:
        """Return recent persisted evaluation results."""

    def list_retrieval_evaluation_results(self) -> RetrievalEvaluationList:
        """Return persisted retrieval-evaluation metrics."""

    def list_ground_truth_evaluation_results(self) -> GroundTruthEvaluationList:
        """Return persisted offline ground-truth answer assessments."""


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
    graph_store: RepositoryGraphStore | None = None,
) -> FastAPI:
    """Create a FastAPI app with injectable runtime dependencies."""
    load_dotenv_environment(keys=("OPENAI_API_KEY", "OPENAI_ADMIN_KEY"))
    app_settings = settings or Settings()
    app = FastAPI(
        title="Repo Deep Research",
        version=package_version(),
        summary="Evidence-grounded research for Python repositories.",
        description=(
            "Repo Deep Research indexes Python repositories, answers direct and "
            "agentic research questions with cited repository evidence, records "
            "monitoring data, and exposes persisted answer-evaluation results."
        ),
        contact={"name": "Repo Deep Research"},
        license_info={"name": "MIT"},
        openapi_tags=OPENAPI_TAGS,
    )
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

    def get_graph_store() -> RepositoryGraphStore:
        return graph_store or create_graph_store(app_settings)

    recording_store_instance = recording_store

    def get_recording_store() -> RecordingStore:
        nonlocal recording_store_instance
        if recording_store_instance is None:
            recording_store_instance = create_recording_store(app_settings)
        return recording_store_instance

    @app.get(
        "/",
        include_in_schema=False,
    )
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get(
        "/health",
        tags=["system"],
        summary="Check dependency health",
        operation_id="get_health",
    )
    async def health() -> dict[str, str | bool]:
        qdrant_ok = False
        try:
            qdrant_ok = get_database().health_check()
        except Exception:
            qdrant_ok = False
        return {"status": "ok" if qdrant_ok else "degraded", "qdrant": qdrant_ok}

    @app.post(
        "/repositories/ingest",
        response_model=IngestSummary,
        tags=["repositories"],
        summary="Ingest and index a repository",
        operation_id="ingest_repository",
    )
    async def ingest_repository(request: RepositoryIngestRequest) -> IngestSummary:
        try:
            return await run_in_threadpool(
                _ingest_repository_sync,
                request,
                app_settings,
                get_database(),
                get_graph_store(),
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

    @app.post(
        "/rag",
        response_model=RagRunResult,
        tags=["answers"],
        summary="Answer with direct RAG",
        operation_id="run_direct_rag",
    )
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

    @app.post(
        "/research",
        response_model=ResearchRunResult,
        tags=["answers"],
        summary="Answer with bounded agentic research",
        operation_id="run_agentic_research",
    )
    async def research(request: ResearchRequest) -> JSONResponse:
        root_path = (request.repository_path or app_settings.repository_root).resolve()
        try:
            repository, _ = discover_repository(
                root_path, app_settings.max_file_size_bytes
            )
            service = create_bounded_research_service(
                settings=app_settings,
                database=get_database(),
                graph_store=get_graph_store(),
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

    @app.get(
        "/repositories/graph-summary",
        response_model=GraphSummary,
        tags=["repositories"],
        summary="Get the current repository graph summary",
        operation_id="get_repository_graph_summary",
    )
    async def repository_graph_summary(
        repository_path: str | None = Query(default=None, min_length=1),
    ) -> GraphSummary:
        root_path = (
            Path(repository_path).resolve()
            if repository_path
            else app_settings.repository_root.resolve()
        )
        try:
            repository, _ = discover_repository(
                root_path, app_settings.max_file_size_bytes
            )
            return (
                get_graph_store()
                .load(
                    repository.repository_id,
                    repository.commit_hash,
                )
                .summary()
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post(
        "/feedback",
        response_model=FeedbackEvent,
        tags=["feedback"],
        summary="Persist answer feedback",
        operation_id="record_feedback",
    )
    async def feedback(request: FeedbackRequest) -> FeedbackEvent:
        event = FeedbackEvent(
            session_id=request.session_id or uuid4().hex,
            request_id=request.request_id,
            run_kind=request.run_kind,
            useful=request.useful,
            comment=request.comment,
            submitted_at=datetime.now(UTC),
        )
        return get_recording_store().record_feedback(event)

    @app.get(
        "/monitoring/summary",
        response_model=MonitoringSummary,
        tags=["monitoring"],
        summary="Get monitoring summary",
        operation_id="get_monitoring_summary",
    )
    async def monitoring_summary() -> MonitoringSummary:
        return get_recording_store().monitoring_summary()

    @app.get(
        "/monitoring/runs",
        response_model=MonitoringRunList,
        tags=["monitoring"],
        summary="List monitoring runs",
        operation_id="list_monitoring_runs",
    )
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

    @app.get(
        "/monitoring/runs/{request_id}",
        response_model=MonitoringRunDetail,
        tags=["monitoring"],
        summary="Get monitoring run detail",
        operation_id="get_monitoring_run_detail",
    )
    async def monitoring_run_detail(request_id: str) -> MonitoringRunDetail:
        detail = get_recording_store().get_monitoring_run(request_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="monitoring run not found")
        return detail

    @app.get(
        "/evaluations/summary",
        response_model=EvaluationDashboardSummary,
        tags=["evaluations"],
        summary="Get evaluation summary",
        operation_id="get_evaluation_summary",
    )
    async def evaluation_summary() -> EvaluationDashboardSummary:
        return get_recording_store().evaluation_summary()

    @app.get(
        "/evaluations/runs",
        response_model=EvaluationRunList,
        tags=["evaluations"],
        summary="List evaluation runs",
        operation_id="list_evaluation_runs",
    )
    async def evaluation_runs(
        limit: int = Query(default=50, ge=1, le=100),
        source_type: EvaluationSourceType | None = None,
        status: EvaluationRunStatus | None = None,
    ) -> EvaluationRunList:
        return get_recording_store().list_evaluation_runs(
            limit=limit,
            source_type=source_type,
            status=status,
        )

    @app.get(
        "/evaluations/results",
        response_model=EvaluationResultList,
        tags=["evaluations"],
        summary="List evaluation results",
        operation_id="list_evaluation_results",
    )
    async def evaluation_results(
        limit: int = Query(default=50, ge=1, le=100),
        source_type: EvaluationSourceType | None = None,
        run_kind: RunKind | None = None,
        context_label: str | None = Query(default=None, min_length=1),
    ) -> EvaluationResultList:
        return get_recording_store().list_evaluation_results(
            limit=limit,
            source_type=source_type,
            run_kind=run_kind,
            context_label=context_label,
        )

    @app.get(
        "/evaluations/retrieval",
        response_model=RetrievalEvaluationList,
        tags=["evaluations"],
        summary="List retrieval evaluation metrics",
        operation_id="list_retrieval_evaluation_results",
    )
    async def retrieval_evaluation_results() -> RetrievalEvaluationList:
        return get_recording_store().list_retrieval_evaluation_results()

    @app.get(
        "/evaluations/ground-truth",
        response_model=GroundTruthEvaluationList,
        tags=["evaluations"],
        summary="List ground-truth evaluation metrics",
        operation_id="list_ground_truth_evaluation_results",
    )
    async def ground_truth_evaluation_results() -> GroundTruthEvaluationList:
        return get_recording_store().list_ground_truth_evaluation_results()

    return app


def _ingest_repository_sync(
    request: RepositoryIngestRequest,
    app_settings: Settings,
    database: RagDatabase,
    graph_store: RepositoryGraphStore,
) -> IngestSummary:
    """Run repository ingestion away from the async server event loop."""
    root_path = materialize_repository_address(
        request.repository_address,
        app_settings.repository_cache_dir,
    )
    repository, files = discover_repository(root_path, app_settings.max_file_size_bytes)
    return ingest_repository_if_needed(
        database=database,
        graph_store=graph_store,
        repository=repository,
        files=files,
    )


def _record_completed_answer(
    *,
    recording_store: RecordingStore,
    run_kind: RunKind,
    answer: RagAnswer | ResearchAnswer,
    trace: RagRunTrace,
) -> None:
    """Persist monitoring metadata and the answer snapshot used by evaluation."""
    version_info = current_app_version_info()
    stamped_trace = trace.model_copy(
        update={
            "answer_app_version": version_info.app_version,
            "answer_git_commit": version_info.git_commit,
            "answer_version_provenance": VersionProvenance(version_info.provenance),
        }
    )
    recording_store.record_run(run_kind=run_kind, trace=stamped_trace)
    recording_store.record_answer_snapshot(
        AnswerSnapshot(
            request_id=stamped_trace.request_id,
            session_id=stamped_trace.session_id,
            run_kind=run_kind,
            question=answer.question,
            answer=answer,
            evidence=answer.evidence,
            repository_id=stamped_trace.repository_id,
            repository_name=stamped_trace.repository_name,
            branch=stamped_trace.branch,
            commit_hash=stamped_trace.commit_hash,
            question_mode=stamped_trace.question_mode,
            retrieval_mode=stamped_trace.retrieval_mode,
            retrieval_limit=stamped_trace.retrieval_limit,
            created_at=stamped_trace.completed_at,
            answer_app_version=stamped_trace.answer_app_version,
            answer_git_commit=stamped_trace.answer_git_commit,
            answer_version_provenance=stamped_trace.answer_version_provenance,
        )
    )


app = create_app()
