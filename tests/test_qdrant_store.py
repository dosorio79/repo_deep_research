"""Qdrant-local integration tests for dense chunk persistence."""

from pathlib import Path
from typing import Any

import pytest
from qdrant_client import QdrantClient

from repo_research import qdrant_store, runtime
from repo_research.config import Settings
from repo_research.models import (
    RepositoryIdentity,
    RetrievalMode,
    SearchQuery,
    create_chunk,
)
from repo_research.qdrant_store import RepositoryDatabase


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


def test_local_fastembed_factories_use_configured_cache_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dense_init: dict[str, Any] = {}
    sparse_init: dict[str, Any] = {}

    class FakeTextEmbedding:
        def __init__(self, *, model_name: str, cache_dir: str) -> None:
            dense_init["model_name"] = model_name
            dense_init["cache_dir"] = cache_dir

        def embed(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
            dense_init["texts"] = texts
            dense_init["batch_size"] = batch_size
            return [[1.0, 0.0, 0.5] for _ in texts]

    class FakeSparseVector:
        indices = [3]
        values = [0.25]

    class FakeSparseTextEmbedding:
        def __init__(self, *, model_name: str, cache_dir: str) -> None:
            sparse_init["model_name"] = model_name
            sparse_init["cache_dir"] = cache_dir

        def embed(self, texts: list[str], *, batch_size: int) -> list[FakeSparseVector]:
            sparse_init["texts"] = texts
            sparse_init["batch_size"] = batch_size
            return [FakeSparseVector() for _ in texts]

    monkeypatch.setattr(qdrant_store, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(qdrant_store, "SparseTextEmbedding", FakeSparseTextEmbedding)
    cache_path = tmp_path / "fastembed"

    dense_embed = qdrant_store.local_embedder("dense-model", 7, cache_path)
    sparse_embed = qdrant_store.local_sparse_embedder("sparse-model", 11, cache_path)

    assert cache_path.is_dir()
    assert dense_init == {
        "model_name": "dense-model",
        "cache_dir": str(cache_path),
    }
    assert sparse_init == {
        "model_name": "sparse-model",
        "cache_dir": str(cache_path),
    }
    assert dense_embed(["hello"]) == [[1.0, 0.0, 0.5]]
    assert dense_init["texts"] == ["hello"]
    assert dense_init["batch_size"] == 7
    assert sparse_embed(["hello"]) == [([3], [0.25])]
    assert sparse_init["texts"] == ["hello"]
    assert sparse_init["batch_size"] == 11


def test_local_fastembed_factories_defer_to_fastembed_default_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dense_init: dict[str, Any] = {}
    sparse_init: dict[str, Any] = {}
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "empty-fastembed"))

    class FakeTextEmbedding:
        def __init__(
            self,
            *,
            model_name: str,
            cache_dir: str | None,
            local_files_only: bool = False,
        ) -> None:
            dense_init["model_name"] = model_name
            dense_init["cache_dir"] = cache_dir
            dense_init["local_files_only"] = local_files_only

        def embed(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
            return [[1.0, 0.0, 0.5] for _ in texts]

    class FakeSparseVector:
        indices = [3]
        values = [0.25]

    class FakeSparseTextEmbedding:
        def __init__(
            self,
            *,
            model_name: str,
            cache_dir: str | None,
            local_files_only: bool = False,
        ) -> None:
            sparse_init["model_name"] = model_name
            sparse_init["cache_dir"] = cache_dir
            sparse_init["local_files_only"] = local_files_only

        def embed(self, texts: list[str], *, batch_size: int) -> list[FakeSparseVector]:
            return [FakeSparseVector() for _ in texts]

    monkeypatch.setattr(qdrant_store, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(qdrant_store, "SparseTextEmbedding", FakeSparseTextEmbedding)

    qdrant_store.local_embedder("dense-model", 7, None)
    qdrant_store.local_sparse_embedder("sparse-model", 11, None)

    assert dense_init == {
        "model_name": "dense-model",
        "cache_dir": None,
        "local_files_only": False,
    }
    assert sparse_init == {
        "model_name": "sparse-model",
        "cache_dir": None,
        "local_files_only": False,
    }


def test_local_fastembed_factories_use_populated_cache_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "fastembed"
    cache_path.mkdir()
    (cache_path / "model-marker").write_text("cached", encoding="utf-8")
    dense_init: dict[str, Any] = {}
    sparse_init: dict[str, Any] = {}

    class FakeTextEmbedding:
        def __init__(
            self,
            *,
            model_name: str,
            cache_dir: str | None,
            local_files_only: bool = False,
        ) -> None:
            dense_init["model_name"] = model_name
            dense_init["cache_dir"] = cache_dir
            dense_init["local_files_only"] = local_files_only

        def embed(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
            return [[1.0, 0.0, 0.5] for _ in texts]

    class FakeSparseVector:
        indices = [3]
        values = [0.25]

    class FakeSparseTextEmbedding:
        def __init__(
            self,
            *,
            model_name: str,
            cache_dir: str | None,
            local_files_only: bool = False,
        ) -> None:
            sparse_init["model_name"] = model_name
            sparse_init["cache_dir"] = cache_dir
            sparse_init["local_files_only"] = local_files_only

        def embed(self, texts: list[str], *, batch_size: int) -> list[FakeSparseVector]:
            return [FakeSparseVector() for _ in texts]

    monkeypatch.setattr(qdrant_store, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(qdrant_store, "SparseTextEmbedding", FakeSparseTextEmbedding)

    qdrant_store.local_embedder("dense-model", 7, cache_path)
    qdrant_store.local_sparse_embedder("sparse-model", 11, cache_path)

    assert dense_init == {
        "model_name": "dense-model",
        "cache_dir": str(cache_path),
        "local_files_only": True,
    }
    assert sparse_init == {
        "model_name": "sparse-model",
        "cache_dir": str(cache_path),
        "local_files_only": True,
    }


def test_local_fastembed_factory_falls_back_when_populated_cache_is_unusable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "fastembed"
    cache_path.mkdir()
    (cache_path / "partial-model").write_text("partial", encoding="utf-8")
    local_only_calls: list[bool] = []

    class FakeTextEmbedding:
        def __init__(
            self,
            *,
            model_name: str,
            cache_dir: str | None,
            local_files_only: bool = False,
        ) -> None:
            local_only_calls.append(local_files_only)
            if local_files_only:
                raise ValueError("cache is incomplete")

        def embed(self, texts: list[str], *, batch_size: int) -> list[list[float]]:
            return [[1.0, 0.0, 0.5] for _ in texts]

    monkeypatch.setattr(qdrant_store, "TextEmbedding", FakeTextEmbedding)

    dense_embed = qdrant_store.local_embedder("dense-model", 7, cache_path)

    assert dense_embed(["hello"]) == [[1.0, 0.0, 0.5]]
    assert local_only_calls == [True, False]


def test_create_database_passes_settings_fastembed_cache_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "fastembed"
    dense_calls: list[tuple[str, int, Path | None]] = []
    sparse_calls: list[tuple[str, int, Path | None]] = []
    database_kwargs: dict[str, Any] = {}

    class FakeRepositoryDatabase:
        def __init__(self, **kwargs: Any) -> None:
            database_kwargs.update(kwargs)

    def fake_dense_embedder(
        model_name: str, batch_size: int, fastembed_cache_path: Path | None
    ) -> qdrant_store.DenseEmbed:
        dense_calls.append((model_name, batch_size, fastembed_cache_path))
        return fake_embed

    def fake_sparse_embedder(
        model_name: str, batch_size: int, fastembed_cache_path: Path | None
    ) -> qdrant_store.SparseEmbed:
        sparse_calls.append((model_name, batch_size, fastembed_cache_path))
        return fake_sparse_embed

    monkeypatch.setattr(runtime, "QdrantClient", lambda *, url: ("qdrant", url))
    monkeypatch.setattr(runtime, "RepositoryDatabase", FakeRepositoryDatabase)
    monkeypatch.setattr(runtime, "local_embedder", fake_dense_embedder)
    monkeypatch.setattr(runtime, "local_sparse_embedder", fake_sparse_embedder)
    settings_kwargs: dict[str, Any] = {
        "_env_file": None,
        "qdrant_url": "http://qdrant.test",
        "qdrant_collection": "test_chunks",
        "embedding_model": "dense-model",
        "embedding_batch_size": 13,
        "sparse_embedding_model": "sparse-model",
        "embedding_dimension": 3,
        "fastembed_cache_path": cache_path,
    }
    settings = Settings(**settings_kwargs)

    database = runtime.create_database(settings)

    assert isinstance(database, FakeRepositoryDatabase)
    assert dense_calls == [("dense-model", 13, cache_path)]
    assert sparse_calls == [("sparse-model", 13, cache_path)]
    assert database_kwargs == {
        "client": ("qdrant", "http://qdrant.test"),
        "collection_name": "test_chunks",
        "embedding_dimension": 3,
        "dense_embed": fake_embed,
        "sparse_embed": fake_sparse_embed,
    }


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


def test_indexed_chunk_count_returns_existing_revision_count() -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=Path("/tmp/sample"),
        branch="main",
        commit_hash="abc123",
    )
    next_commit = repository.model_copy(update={"commit_hash": "def456"})
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

    assert (
        database.indexed_chunk_count(repository.repository_id, repository.commit_hash)
        == 0
    )

    database.replace(repository.repository_id, [cost_chunk, search_chunk])

    assert (
        database.indexed_chunk_count(repository.repository_id, repository.commit_hash)
        == 2
    )
    assert (
        database.indexed_chunk_count(next_commit.repository_id, next_commit.commit_hash)
        == 0
    )


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
