"""Typed system-boundary models for repository research."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, model_validator


class RepositoryIdentity(BaseModel):
    """The immutable source revision that a set of chunks describes."""

    name: str = Field(min_length=1)
    root_path: Path
    branch: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)

    @property
    def repository_id(self) -> str:
        """Return a stable identifier for this local repository location."""
        value = str(self.root_path.resolve())
        return sha256(value.encode()).hexdigest()


class ParsedChunk(BaseModel):
    """A retrievable source fragment with verifiable repository metadata."""

    chunk_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    path: str = Field(min_length=1)
    language: str = Field(min_length=1)
    chunk_type: str = Field(min_length=1)
    symbol: str | None = None
    parent_symbol: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str = Field(min_length=1)
    context: dict[str, str | list[str]] = Field(default_factory=dict)
    content_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_line_range(self) -> ParsedChunk:
        """Ensure source references always name a non-empty, ordered range."""
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class SearchQuery(BaseModel):
    """A dense-search request scoped to one repository."""

    text: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    """A normalized dense-search result returned to callers."""

    chunk: ParsedChunk
    score: float


class IngestionIssue(BaseModel):
    """A path-scoped reason an otherwise eligible file was not indexed."""

    path: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class IngestSummary(BaseModel):
    """The observable result of one repository indexing operation."""

    repository: RepositoryIdentity
    indexed_chunks: int = Field(ge=0)
    skipped_files: list[IngestionIssue] = Field(default_factory=list)
    index_updated: bool = True


class ParsedFiles(BaseModel):
    """Successful chunks and diagnostics from parsing a repository file set."""

    chunks: list[ParsedChunk] = Field(default_factory=list)
    skipped_files: list[IngestionIssue] = Field(default_factory=list)


def create_chunk(
    *,
    repository: RepositoryIdentity,
    path: str,
    language: str,
    chunk_type: str,
    start_line: int,
    end_line: int,
    content: str,
    symbol: str | None = None,
    parent_symbol: str | None = None,
    context: dict[str, str | list[str]] | None = None,
) -> ParsedChunk:
    """Create a chunk with deterministic content and point identifiers."""
    content_hash = sha256(content.encode()).hexdigest()
    identity = "|".join(
        [
            repository.repository_id,
            repository.commit_hash,
            path,
            chunk_type,
            symbol or "",
            str(start_line),
            str(end_line),
            content_hash,
        ]
    )
    return ParsedChunk(
        chunk_id=str(uuid5(NAMESPACE_URL, identity)),
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        path=path,
        language=language,
        chunk_type=chunk_type,
        symbol=symbol,
        parent_symbol=parent_symbol,
        start_line=start_line,
        end_line=end_line,
        content=content,
        context=context or {},
        content_hash=content_hash,
    )
