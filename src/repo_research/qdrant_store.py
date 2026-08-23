"""Local embeddings and Qdrant dense, sparse, and hybrid repository retrieval."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models

from repo_research.models import ParsedChunk, RetrievalMode, SearchQuery, SearchResult

DenseEmbed = Callable[[list[str]], list[list[float]]]
SparseEmbed = Callable[[list[str]], list[tuple[list[int], list[float]]]]


def local_embedder(
    model_name: str, batch_size: int, cache_path: Path | None
) -> DenseEmbed:
    """Create a local FastEmbed/ONNX embedding function."""
    cache_dir = _prepare_fastembed_cache_dir(cache_path)
    model = _create_fastembed_model(
        TextEmbedding, model_name=model_name, cache_dir=cache_dir, cache_path=cache_path
    )

    def embed(texts: list[str]) -> list[list[float]]:
        return [list(vector) for vector in model.embed(texts, batch_size=batch_size)]

    return embed


def local_sparse_embedder(
    model_name: str, batch_size: int, cache_path: Path | None
) -> SparseEmbed:
    """Create a local FastEmbed sparse encoder compatible with Qdrant."""
    cache_dir = _prepare_fastembed_cache_dir(cache_path)
    model = _create_fastembed_model(
        SparseTextEmbedding,
        model_name=model_name,
        cache_dir=cache_dir,
        cache_path=cache_path,
    )

    def embed(texts: list[str]) -> list[tuple[list[int], list[float]]]:
        return [
            (
                [int(index) for index in vector.indices],
                [float(value) for value in vector.values],
            )
            for vector in model.embed(texts, batch_size=batch_size)
        ]

    return embed


def _prepare_fastembed_cache_dir(cache_path: Path | None) -> str | None:
    if cache_path is None:
        return None
    if cache_path.exists() and not cache_path.is_dir():
        raise ValueError(
            "RDR_FASTEMBED_CACHE_PATH must point to a directory, "
            f"but {cache_path} exists and is not a directory"
        )
    cache_path.mkdir(parents=True, exist_ok=True)
    return str(cache_path)


def _create_fastembed_model(
    model_class: type[Any],
    *,
    model_name: str,
    cache_dir: str | None,
    cache_path: Path | None,
) -> Any:
    if _fastembed_cache_is_populated(cache_path):
        try:
            return model_class(
                model_name=model_name,
                cache_dir=cache_dir,
                local_files_only=True,
            )
        except ValueError:
            pass
    return model_class(model_name=model_name, cache_dir=cache_dir)


def _fastembed_cache_is_populated(cache_path: Path | None) -> bool:
    cache_root = _resolve_fastembed_cache_path(cache_path)
    try:
        return cache_root.is_dir() and any(cache_root.iterdir())
    except OSError:
        return False


def _resolve_fastembed_cache_path(cache_path: Path | None) -> Path:
    if cache_path is not None:
        return cache_path
    env_cache_path = os.getenv("FASTEMBED_CACHE_PATH")
    if env_cache_path:
        return Path(env_cache_path)
    return Path(tempfile.gettempdir()) / "fastembed_cache"


class RepositoryDatabase:
    """Persist chunks and retrieve them with dense, sparse, or hybrid search."""

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding_dimension: int,
        dense_embed: DenseEmbed,
        sparse_embed: SparseEmbed,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._embedding_dimension = embedding_dimension
        self._dense_embed = dense_embed
        self._sparse_embed = sparse_embed

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        """Safely replace current chunks while retaining the prior index on failure."""
        self._ensure_collection()
        existing_ids = self._existing_chunk_ids(repository_id)
        dense_vectors = (
            self._dense_embed([chunk.content for chunk in chunks]) if chunks else []
        )
        sparse_vectors = (
            self._sparse_embed([chunk.content for chunk in chunks]) if chunks else []
        )
        if len(dense_vectors) != len(chunks):
            raise ValueError(
                "dense embedder returned a different number of vectors than chunks"
            )
        if len(sparse_vectors) != len(chunks):
            raise ValueError(
                "sparse embedder returned a different number of vectors than chunks"
            )
        if any(len(vector) != self._embedding_dimension for vector in dense_vectors):
            raise ValueError(
                "dense embedder returned a vector with an unexpected dimension"
            )
        _validate_sparse_vectors(sparse_vectors)
        if chunks:
            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    models.PointStruct(
                        id=chunk.chunk_id,
                        vector={
                            "dense": dense_vector,
                            "sparse": models.SparseVector(
                                indices=sparse_vector[0], values=sparse_vector[1]
                            ),
                        },
                        payload=chunk.model_dump(mode="json"),
                    )
                    for chunk, dense_vector, sparse_vector in zip(
                        chunks, dense_vectors, sparse_vectors, strict=True
                    )
                ],
                wait=True,
            )
        incoming_ids = {chunk.chunk_id for chunk in chunks}
        stale_ids = [
            point_id for point_id in existing_ids if point_id not in incoming_ids
        ]
        if stale_ids:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(points=stale_ids),
                wait=True,
            )

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        """Return how many chunks are already indexed for a repository revision."""
        if not self._client.collection_exists(self._collection_name):
            return 0
        response = self._client.count(
            collection_name=self._collection_name,
            count_filter=_revision_filter(repository_id, commit_hash),
            exact=True,
        )
        return response.count

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return typed results from the requested mode and repository revision."""
        repository_filter = _revision_filter(query.repository_id, query.commit_hash)
        if query.mode is RetrievalMode.DENSE:
            response = self._client.query_points(
                collection_name=self._collection_name,
                query=self._dense_embed([query.text])[0],
                using="dense",
                query_filter=repository_filter,
                limit=query.limit,
                with_payload=True,
            )
        elif query.mode is RetrievalMode.SPARSE:
            indices, values = self._sparse_embed([query.text])[0]
            response = self._client.query_points(
                collection_name=self._collection_name,
                query=models.SparseVector(indices=indices, values=values),
                using="sparse",
                query_filter=repository_filter,
                limit=query.limit,
                with_payload=True,
            )
        else:
            dense_vector = self._dense_embed([query.text])[0]
            sparse_indices, sparse_values = self._sparse_embed([query.text])[0]
            candidate_limit = query.limit * 4
            response = self._client.query_points(
                collection_name=self._collection_name,
                prefetch=[
                    models.Prefetch(
                        query=dense_vector,
                        using="dense",
                        filter=repository_filter,
                        limit=candidate_limit,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices, values=sparse_values
                        ),
                        using="sparse",
                        filter=repository_filter,
                        limit=candidate_limit,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=query.limit,
                with_payload=True,
            )
        return [
            SearchResult(
                chunk=ParsedChunk.model_validate(point.payload), score=point.score
            )
            for point in response.points
        ]

    def get_chunks(
        self, repository_id: str, commit_hash: str, chunk_ids: list[str]
    ) -> list[ParsedChunk]:
        """Return indexed chunks by ID without semantic search or embeddings."""
        if not chunk_ids or not self._client.collection_exists(self._collection_name):
            return []
        unique_ids = list(dict.fromkeys(chunk_ids))
        points = self._client.retrieve(
            collection_name=self._collection_name,
            ids=unique_ids,
            with_payload=True,
            with_vectors=False,
        )
        chunks_by_id: dict[str, ParsedChunk] = {}
        for point in points:
            if point.payload is None:
                continue
            chunk = ParsedChunk.model_validate(point.payload)
            if (
                chunk.repository_id == repository_id
                and chunk.commit_hash == commit_hash
            ):
                chunks_by_id[chunk.chunk_id] = chunk
        return [
            chunks_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in chunks_by_id
        ]

    def health_check(self) -> bool:
        """Return whether Qdrant responds to a lightweight collection request."""
        return bool(self._client.get_collections())

    def _existing_chunk_ids(self, repository_id: str) -> list[models.ExtendedPointId]:
        """Return all current point IDs before a replacement is staged."""
        point_ids: list[models.ExtendedPointId] = []
        offset: models.ExtendedPointId | None = None
        repository_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_id",
                    match=models.MatchValue(value=repository_id),
                )
            ]
        )
        while True:
            points, next_offset = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=repository_filter,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.extend(point.id for point in points)
            if next_offset is None:
                return point_ids
            offset = next_offset

    def _ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=self._embedding_dimension,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={"sparse": models.SparseVectorParams()},
            )


def _revision_filter(repository_id: str, commit_hash: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="repository_id",
                match=models.MatchValue(value=repository_id),
            ),
            models.FieldCondition(
                key="commit_hash",
                match=models.MatchValue(value=commit_hash),
            ),
        ]
    )


def _validate_sparse_vectors(vectors: list[tuple[list[int], list[float]]]) -> None:
    for indices, values in vectors:
        if len(indices) != len(values):
            raise ValueError("sparse embedder returned mismatched indices and values")
        if any(index < 0 for index in indices):
            raise ValueError("sparse embedder returned a negative index")
