"""Shared structural protocols for repository storage boundaries."""

from __future__ import annotations

from typing import Protocol

from repo_research.models import ParsedChunk, SearchQuery, SearchResult


class RepositorySearcher(Protocol):
    """Repository retrieval dependency used by RAG, research, and evaluation."""

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return typed repository evidence for one query."""


class RepositoryIndexer(Protocol):
    """Repository indexing dependency used by ingestion entry points."""

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        """Replace current indexed chunks for one repository identity."""

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        """Return indexed chunk count for one repository revision."""
