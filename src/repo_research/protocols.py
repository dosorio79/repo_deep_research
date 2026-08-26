"""Shared structural protocols for repository storage boundaries."""

from __future__ import annotations

from typing import Protocol

from repo_research.graph_models import GraphSummary, RepositoryGraph
from repo_research.models import ParsedChunk, SearchQuery, SearchResult


class RepositorySearcher(Protocol):
    """Repository retrieval dependency used by RAG, research, and evaluation."""

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return typed repository evidence for one query."""

    def get_chunks(
        self, repository_id: str, commit_hash: str, chunk_ids: list[str]
    ) -> list[ParsedChunk]:
        """Return canonical chunks for a repository revision by chunk ID."""


class RepositoryIndexer(Protocol):
    """Repository indexing dependency used by ingestion entry points."""

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        """Replace current indexed chunks for one repository identity."""

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        """Return indexed chunk count for one repository revision."""


class RepositoryGraphStore(Protocol):
    """Repository graph artifact dependency used by ingestion and research."""

    def write(self, graph: RepositoryGraph) -> GraphSummary:
        """Persist a graph and return its summary."""

    def load(self, repository_id: str, commit_hash: str) -> RepositoryGraph:
        """Load a graph for one repository revision."""

    def exists(self, repository_id: str, commit_hash: str) -> bool:
        """Return whether a valid graph exists for one revision."""
