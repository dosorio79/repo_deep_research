"""Runtime composition for CLI and API entry points."""

from __future__ import annotations

from qdrant_client import QdrantClient

from repo_research.config import Settings
from repo_research.qdrant_store import (
    RepositoryDatabase,
    local_embedder,
    local_sparse_embedder,
)
from repo_research.protocols import RepositorySearcher
from repo_research.rag import (
    AnswerGenerator,
    DirectRagService,
    OpenAIResponsesModel,
)
from repo_research.research import (
    BoundedResearchService,
    PydanticAIResearchAgent,
    ResearchAgentRunner,
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


def create_research_agent(settings: Settings) -> PydanticAIResearchAgent:
    """Create the live PydanticAI research agent adapter."""
    return PydanticAIResearchAgent(model=settings.openai_answer_model)


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


def create_bounded_research_service(
    *,
    settings: Settings,
    database: RepositorySearcher | None = None,
    agent: ResearchAgentRunner | None = None,
) -> BoundedResearchService:
    """Create the bounded agentic research service used by CLI and API."""
    return BoundedResearchService(
        database=database or create_database(settings),
        agent=agent or create_research_agent(settings),
    )
