"""Typed system-boundary models for repository research."""

from __future__ import annotations

from enum import StrEnum
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


class RetrievalMode(StrEnum):
    """The supported repository retrieval strategies."""

    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"


class ResearchMode(StrEnum):
    """The supported answer intents for direct repository research."""

    LOCATE = "locate"
    FLOW = "flow"
    CHANGE = "change"
    AUTO = "auto"


class SearchQuery(BaseModel):
    """A repository search request scoped to one source revision."""

    text: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    mode: RetrievalMode = RetrievalMode.DENSE


class SearchResult(BaseModel):
    """A normalized retrieval result returned by every search mode."""

    chunk: ParsedChunk
    score: float


class ResearchRequest(BaseModel):
    """A direct-RAG research request scoped by CLI or API orchestration."""

    question: str = Field(min_length=1)
    repository_path: Path | None = None
    mode: ResearchMode = ResearchMode.AUTO
    retrieval_mode: RetrievalMode = RetrievalMode.DENSE
    limit: int = Field(default=5, ge=1, le=20)


class EvidenceItem(BaseModel):
    """A canonical citation derived from a retrieved repository chunk."""

    evidence_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    score: float
    reason: str = Field(min_length=1)


class ChangeTarget(BaseModel):
    """A file or symbol that may need changes, grounded by evidence."""

    path: str = Field(min_length=1)
    symbol: str | None = None
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ResearchAnswer(BaseModel):
    """A grounded direct-RAG answer with validated repository citations."""

    question: str = Field(min_length=1)
    mode: ResearchMode
    summary: str = Field(min_length=1)
    implementation_flow: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    relevant_symbols: list[str] = Field(default_factory=list)
    change_targets: list[ChangeTarget] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class EvaluationRecord(BaseModel):
    """One manually verified retrieval question and its expected evidence."""

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    relevant_files: list[str] = Field(min_length=1)
    relevant_symbols: list[str] = Field(default_factory=list)
    notes: str = ""


class EvaluationResult(BaseModel):
    """Aggregate retrieval metrics for a dataset and one retrieval mode."""

    dataset: str = Field(min_length=1)
    mode: RetrievalMode
    limit: int = Field(ge=1)
    record_count: int = Field(ge=0)
    file_hit_rate: float = Field(ge=0, le=1)
    file_mrr: float = Field(ge=0, le=1)
    file_recall: float = Field(ge=0, le=1)
    file_precision: float = Field(ge=0, le=1)
    symbol_hit_rate: float = Field(ge=0, le=1)


class AnswerEvaluationResult(BaseModel):
    """LLM-judge scores for one grounded direct-RAG answer."""

    record_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    correctness: float = Field(ge=0, le=5)
    groundedness: float = Field(ge=0, le=5)
    citation_accuracy: float = Field(ge=0, le=5)
    completeness: float = Field(ge=0, le=5)
    usefulness: float = Field(ge=0, le=5)
    unsupported_claim_count: int = Field(ge=0)
    notes: str = ""


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
