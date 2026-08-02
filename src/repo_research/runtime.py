"""Runtime composition for CLI and API entry points."""

from __future__ import annotations

from qdrant_client import QdrantClient

from repo_research.config import Settings
from repo_research.db import RepositoryDatabase, local_embedder, local_sparse_embedder
from repo_research.rag import (
    AnswerGenerator,
    DirectRagService,
    OpenAIResponsesModel,
    RepositorySearcher,
)


def create_database(settings: Settings) -> RepositoryDatabase:
    """Create the repository storage and retrieval dependency."""
    return RepositoryDatabase(
        client=QdrantClient(url=settings.qdrant_url),
        collection_name=settings.qdrant_collection,
        embedding_dimension=settings.embedding_dimension,
        dense_embed=local_embedder(
            settings.embedding_model, settings.embedding_batch_size
        ),
        sparse_embed=local_sparse_embedder(
            settings.sparse_embedding_model, settings.embedding_batch_size
        ),
    )


def create_answer_model(settings: Settings) -> OpenAIResponsesModel:
    """Create the live OpenAI answer and judge adapter."""
    return OpenAIResponsesModel(
        answer_model=settings.openai_answer_model,
        judge_model=settings.openai_judge_model,
    )


def create_direct_rag_service(
    *,
    settings: Settings,
    database: RepositorySearcher | None = None,
    generator: AnswerGenerator | None = None,
) -> DirectRagService:
    """Create the common direct-RAG service used by CLI and API."""
    return DirectRagService(
        database=database or create_database(settings),
        generator=generator or create_answer_model(settings),
    )
