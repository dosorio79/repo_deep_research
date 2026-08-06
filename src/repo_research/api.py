"""Minimal FastAPI backend for M3 grounded direct RAG."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAIError
from qdrant_client.http.exceptions import ResponseHandlingException

from repo_research.config import Settings, load_dotenv_environment
from repo_research.ingestion import (
    discover_repository,
    materialize_repository_address,
    parse_files,
)
from repo_research.models import (
    IngestSummary,
    ParsedChunk,
    RagRequest,
    RagRunResult,
    RepositoryIngestRequest,
    ResearchRequest,
    ResearchRunResult,
    SearchQuery,
    SearchResult,
)
from repo_research.rag import AnswerGenerator
from repo_research.research import ResearchAgentRunner
from repo_research.runtime import (
    create_answer_model,
    create_bounded_research_service,
    create_database,
    create_direct_rag_service,
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
) -> FastAPI:
    """Create a FastAPI app with injectable runtime dependencies."""
    load_dotenv_environment(keys=("OPENAI_API_KEY", "OPENAI_ADMIN_KEY"))
    app_settings = settings or Settings()
    app = FastAPI(title="Repo Deep Research", version=package_version())
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
            existing_chunk_count = get_database().indexed_chunk_count(
                repository.repository_id,
                repository.commit_hash,
            )
            if _can_reuse_index(repository.commit_hash, existing_chunk_count):
                return IngestSummary(
                    repository=repository,
                    indexed_chunks=existing_chunk_count,
                    skipped_files=[],
                    index_updated=False,
                )
            parsed_files = parse_files(files, repository)
            index_updated = bool(parsed_files.chunks or not parsed_files.skipped_files)
            if index_updated:
                get_database().replace(repository.repository_id, parsed_files.chunks)
            return IngestSummary(
                repository=repository,
                indexed_chunks=len(parsed_files.chunks),
                skipped_files=parsed_files.skipped_files,
                index_updated=index_updated,
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
            return service.run(
                repository=repository,
                request=request.model_copy(update={"repository_path": root_path}),
            )
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
    async def research(request: ResearchRequest) -> ResearchRunResult:
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
            return service.run(
                repository=repository,
                request=request.model_copy(update={"repository_path": root_path}),
            )
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

    return app


def _can_reuse_index(commit_hash: str, indexed_chunk_count: int) -> bool:
    return indexed_chunk_count > 0 and not commit_hash.startswith("unknown-")


app = create_app()
