"""Qdrant-local integration tests for dense chunk persistence."""

from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from repo_research.db import RepositoryDatabase
from repo_research.models import (
    RepositoryIdentity,
    RetrievalMode,
    SearchQuery,
    create_chunk,
)


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Return deterministic three-dimensional test vectors."""
    vectors = []
    for text in texts:
        lowered = text.lower()
        vectors.append(
            [
                float(lowered.count("cost")),
                float(lowered.count("search")),
                1.0,
            ]
        )
    return vectors


def wrong_dimension_embed(texts: list[str]) -> list[list[float]]:
    """Return vectors that cannot be stored in the configured collection."""
    return [[1.0, 0.0] for _ in texts]


def fake_sparse_embed(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """Return deterministic sparse vectors for dense/sparse/hybrid tests."""
    vectors = []
    for text in texts:
        lowered = text.lower()
        indices: list[int] = []
        values: list[float] = []
        for index, term in enumerate(["cost", "search"]):
            count = lowered.count(term)
            if count:
                indices.append(index)
                values.append(float(count))
        vectors.append((indices, values))
    return vectors


def malformed_sparse_embed(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """Return invalid sparse vectors for replacement-safety coverage."""
    return [([1], [1.0, 2.0]) for _ in texts]


def test_replace_repository_is_idempotent_and_search_returns_typed_evidence() -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=Path("/tmp/sample"),
        branch="main",
        commit_hash="abc123",
    )
    cost_chunk = create_chunk(
        repository=repository,
        path="costs.py",
        language="python",
        chunk_type="function",
        symbol="calculate_cost",
        start_line=1,
        end_line=2,
        content="def calculate_cost():\n    return cost\n",
    )
    search_chunk = create_chunk(
        repository=repository,
        path="search.py",
        language="python",
        chunk_type="function",
        symbol="search_repository",
        start_line=1,
        end_line=2,
        content="def search_repository():\n    return search\n",
    )
    client = QdrantClient(":memory:")
    database = RepositoryDatabase(client, "chunks", 3, fake_embed, fake_sparse_embed)

    database.replace(repository.repository_id, [cost_chunk, search_chunk])
    database.replace(repository.repository_id, [cost_chunk])
    for mode in RetrievalMode:
        results = database.search(
            SearchQuery(
                text="cost",
                repository_id=repository.repository_id,
                commit_hash=repository.commit_hash,
                limit=5,
                mode=mode,
            )
        )

        assert [result.chunk.path for result in results] == ["costs.py"]
        assert results[0].chunk.symbol == "calculate_cost"


def test_replace_preserves_existing_points_when_embedding_validation_fails() -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=Path("/tmp/sample"),
        branch="main",
        commit_hash="abc123",
    )
    existing_chunk = create_chunk(
        repository=repository,
        path="costs.py",
        language="python",
        chunk_type="function",
        symbol="calculate_cost",
        start_line=1,
        end_line=2,
        content="def calculate_cost():\n    return cost\n",
    )
    replacement_chunk = create_chunk(
        repository=repository,
        path="search.py",
        language="python",
        chunk_type="function",
        symbol="search_repository",
        start_line=1,
        end_line=2,
        content="def search_repository():\n    return search\n",
    )
    client = QdrantClient(":memory:")
    working_database = RepositoryDatabase(
        client, "chunks", 3, fake_embed, fake_sparse_embed
    )
    failing_database = RepositoryDatabase(
        client, "chunks", 3, wrong_dimension_embed, fake_sparse_embed
    )
    working_database.replace(repository.repository_id, [existing_chunk])

    with pytest.raises(ValueError, match="unexpected dimension"):
        failing_database.replace(repository.repository_id, [replacement_chunk])

    results = working_database.search(
        SearchQuery(
            text="cost",
            repository_id=repository.repository_id,
            commit_hash=repository.commit_hash,
        )
    )
    assert [result.chunk.path for result in results] == ["costs.py"]


def test_replace_preserves_existing_points_when_sparse_embedding_is_malformed() -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=Path("/tmp/sample"),
        branch="main",
        commit_hash="abc123",
    )
    chunk = create_chunk(
        repository=repository,
        path="costs.py",
        language="python",
        chunk_type="function",
        symbol="calculate_cost",
        start_line=1,
        end_line=2,
        content="def calculate_cost():\n    return cost\n",
    )
    client = QdrantClient(":memory:")
    working_database = RepositoryDatabase(
        client, "chunks", 3, fake_embed, fake_sparse_embed
    )
    failing_database = RepositoryDatabase(
        client, "chunks", 3, fake_embed, malformed_sparse_embed
    )
    working_database.replace(repository.repository_id, [chunk])

    with pytest.raises(ValueError, match="mismatched indices"):
        failing_database.replace(repository.repository_id, [chunk])

    results = working_database.search(
        SearchQuery(
            text="cost",
            repository_id=repository.repository_id,
            commit_hash=repository.commit_hash,
            mode=RetrievalMode.HYBRID,
        )
    )
    assert [result.chunk.path for result in results] == ["costs.py"]
