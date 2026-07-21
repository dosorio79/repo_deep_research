"""Local ONNX embeddings and Qdrant persistence for repository chunks."""

from __future__ import annotations

from collections.abc import Callable

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

from repo_research.models import ParsedChunk, SearchQuery, SearchResult

Embed = Callable[[list[str]], list[list[float]]]


def local_embedder(model_name: str, batch_size: int) -> Embed:
    """Create a local FastEmbed/ONNX embedding function."""
    model = TextEmbedding(model_name=model_name)

    def embed(texts: list[str]) -> list[list[float]]:
        return [list(vector) for vector in model.embed(texts, batch_size=batch_size)]

    return embed


class RepositoryDatabase:
    """Replace and densely search the current chunks in one Qdrant collection."""

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding_dimension: int,
        embed: Embed,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._embedding_dimension = embedding_dimension
        self._embed = embed

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        """Replace all current points for a repository, keeping ingestion idempotent."""
        self._ensure_collection()
        repository_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="repository_id",
                    match=models.MatchValue(value=repository_id),
                )
            ]
        )
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(filter=repository_filter),
            wait=True,
        )
        if not chunks:
            return

        vectors = self._embed([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError(
                "embedder returned a different number of vectors than chunks"
            )
        self._client.upsert(
            collection_name=self._collection_name,
            points=[
                models.PointStruct(
                    id=chunk.chunk_id,
                    vector=vector,
                    payload=chunk.model_dump(mode="json"),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
            wait=True,
        )

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return typed dense search results scoped to one repository."""
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=self._embed([query.text])[0],
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="repository_id",
                        match=models.MatchValue(value=query.repository_id),
                    )
                ]
            ),
            limit=query.limit,
            with_payload=True,
        )
        return [
            SearchResult(
                chunk=ParsedChunk.model_validate(point.payload), score=point.score
            )
            for point in response.points
        ]

    def _ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=self._embedding_dimension,
                    distance=models.Distance.COSINE,
                ),
            )
