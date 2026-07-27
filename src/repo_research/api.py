"""Minimal FastAPI backend for M3 grounded research."""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, HTTPException

from repo_research.cli import _create_database, _create_openai_model
from repo_research.config import Settings
from repo_research.ingestion import discover_repository
from repo_research.models import (
    ResearchAnswer,
    ResearchRequest,
    SearchQuery,
    SearchResult,
)
from repo_research.research import AnswerGenerator, ResearchService


class ResearchDatabase(Protocol):
    """Database behavior required by the API routes."""

    def health_check(self) -> bool:
        """Return dependency health."""

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return repository search results."""


def create_app(
    *,
    settings: Settings | None = None,
    database: ResearchDatabase | None = None,
    generator: AnswerGenerator | None = None,
) -> FastAPI:
    """Create a FastAPI app with injectable runtime dependencies."""
    app_settings = settings or Settings()
    app = FastAPI(title="Repo Deep Research", version="0.1.0")

    def get_database() -> ResearchDatabase:
        return database or _create_database(app_settings)

    def get_generator() -> AnswerGenerator:
        return generator or _create_openai_model(app_settings)

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        qdrant_ok = False
        try:
            qdrant_ok = get_database().health_check()
        except Exception:
            qdrant_ok = False
        return {"status": "ok" if qdrant_ok else "degraded", "qdrant": qdrant_ok}

    @app.post("/research", response_model=ResearchAnswer)
    def research(request: ResearchRequest) -> ResearchAnswer:
        root_path = (request.repository_path or app_settings.repository_root).resolve()
        try:
            repository, _ = discover_repository(
                root_path, app_settings.max_file_size_bytes
            )
            service = ResearchService(
                database=get_database(),
                generator=get_generator(),
            )
            return service.research(
                repository=repository,
                request=request.model_copy(update={"repository_path": root_path}),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app


app = create_app()
