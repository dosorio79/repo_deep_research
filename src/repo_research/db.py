"""Local embeddings and Qdrant dense, sparse, and hybrid repository retrieval."""

from __future__ import annotations

from collections.abc import Callable

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models

from repo_research.models import ParsedChunk, RetrievalMode, SearchQuery, SearchResult

DenseEmbed = Callable[[list[str]], list[list[float]]]
SparseEmbed = Callable[[list[str]], list[tuple[list[int], list[float]]]]


def local_embedder(model_name: str, batch_size: int) -> DenseEmbed:
    """Create a local FastEmbed/ONNX embedding function."""
    model = TextEmbedding(model_name=model_name)

    def embed(texts: list[str]) -> list[list[float]]:
        return [list(vector) for vector in model.embed(texts, batch_size=batch_size)]

    return embed


def local_sparse_embedder(model_name: str, batch_size: int) -> SparseEmbed:
    """Create a local FastEmbed sparse encoder compatible with Qdrant."""
    model = SparseTextEmbedding(model_name=model_name)

    def embed(texts: list[str]) -> list[tuple[list[int], list[float]]]:
        return [
            (
                [int(index) for index in vector.indices],
                [float(value) for value in vector.values],
            )
            for vector in model.embed(texts, batch_size=batch_size)
        ]

    return embed


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

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return typed results from the requested mode and repository revision."""
        repository_filter = _repository_filter(query)
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


def _repository_filter(query: SearchQuery) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="repository_id",
                match=models.MatchValue(value=query.repository_id),
            ),
            models.FieldCondition(
                key="commit_hash",
                match=models.MatchValue(value=query.commit_hash),
            ),
        ]
    )


def _validate_sparse_vectors(vectors: list[tuple[list[int], list[float]]]) -> None:
    for indices, values in vectors:
        if len(indices) != len(values):
            raise ValueError("sparse embedder returned mismatched indices and values")
        if any(index < 0 for index in indices):
            raise ValueError("sparse embedder returned a negative index")
