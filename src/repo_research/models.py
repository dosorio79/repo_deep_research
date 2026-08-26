"""Typed system-boundary models for repository evidence and RAG answers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import AliasChoices, BaseModel, Field, model_validator


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


class RagMode(StrEnum):
    """The supported answer intents for direct RAG."""

    LOCATE = "locate"
    FLOW = "flow"
    CHANGE = "change"
    AUTO = "auto"


class RunKind(StrEnum):
    """The persisted run categories shown in monitoring dashboards."""

    DIRECT = "direct"
    AGENTIC = "agentic"


class VersionProvenance(StrEnum):
    """How persisted application version metadata was determined."""

    EXACT = "exact"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class EvaluationSourceType(StrEnum):
    """Sources that can feed an answer-quality evaluation run."""

    DATASET = "dataset"
    MONITORED_RUNS = "monitored_runs"


class EvaluationRunStatus(StrEnum):
    """Lifecycle state for a persisted evaluation batch."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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


class RagRequest(BaseModel):
    """A direct-RAG request scoped by CLI or API orchestration."""

    question: str = Field(min_length=1)
    repository_path: Path | None = None
    mode: RagMode = RagMode.AUTO
    retrieval_mode: RetrievalMode = RetrievalMode.DENSE
    limit: int = Field(default=5, ge=1, le=20)
    session_id: str | None = Field(default=None, min_length=1)


class ResearchBudget(BaseModel):
    """Configurable tool-call limits for one bounded research run."""

    max_searches: int = Field(default=5, ge=1, le=20)
    max_file_reads: int = Field(default=6, ge=0, le=20)
    max_total_tool_calls: int = Field(default=12, ge=1, le=40)
    max_graph_expansions: int = Field(default=2, ge=0, le=10)
    max_graph_nodes: int = Field(default=12, ge=1, le=50)
    max_graph_depth: int = Field(default=2, ge=0, le=2)

    @model_validator(mode="after")
    def validate_total_budget(self) -> ResearchBudget:
        """Ensure each per-tool allowance can fit under the total call limit."""
        if self.max_total_tool_calls < self.max_searches:
            raise ValueError("max_total_tool_calls must cover max_searches")
        if self.max_total_tool_calls < self.max_file_reads:
            raise ValueError("max_total_tool_calls must cover max_file_reads")
        return self


class ResearchRequest(BaseModel):
    """An agentic-research request scoped by CLI or API orchestration."""

    question: str = Field(min_length=1)
    repository_path: Path | None = None
    mode: RagMode = RagMode.CHANGE
    retrieval_mode: RetrievalMode = RetrievalMode.DENSE
    retrieval_limit: int = Field(default=5, ge=1, le=20)
    budget: ResearchBudget = Field(default_factory=ResearchBudget)
    session_id: str | None = Field(default=None, min_length=1)


class RepositoryIngestRequest(BaseModel):
    """A request to parse and index a repository available to the backend."""

    repository_address: str = Field(
        min_length=1,
        validation_alias=AliasChoices("repository_address", "repository_path"),
    )


class EvidenceItem(BaseModel):
    """A canonical citation derived from a retrieved repository chunk."""

    evidence_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    score: float
    reason: str = Field(min_length=1)
    content: str | None = None
    chunk_id: str | None = Field(default=None, min_length=1)


class ChangeTarget(BaseModel):
    """A file or symbol that may need changes, grounded by evidence."""

    path: str = Field(min_length=1)
    symbol: str | None = None
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class RagAnswer(BaseModel):
    """A grounded direct-RAG answer with validated repository citations."""

    question: str = Field(min_length=1)
    mode: RagMode
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


class ResearchStep(BaseModel):
    """One application-recorded step in a bounded research process."""

    sequence: int = Field(ge=1)
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ResearchAnswer(BaseModel):
    """A grounded agentic-research answer with explicit process steps."""

    question: str = Field(min_length=1)
    mode: RagMode = RagMode.CHANGE
    summary: str = Field(min_length=1)
    research_steps: list[ResearchStep] = Field(default_factory=list)
    implementation_flow: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    relevant_symbols: list[str] = Field(default_factory=list)
    change_targets: list[ChangeTarget] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False

    @model_validator(mode="after")
    def validate_evidence_references(self) -> ResearchAnswer:
        """Ensure process steps and change targets cite returned evidence only."""
        evidence_ids: set[str] = set()
        duplicates: set[str] = set()
        for item in self.evidence:
            if item.evidence_id in evidence_ids:
                duplicates.add(item.evidence_id)
            evidence_ids.add(item.evidence_id)
        if duplicates:
            raise ValueError(f"duplicate evidence IDs: {sorted(duplicates)}")
        referenced_ids = {
            evidence_id
            for step in self.research_steps
            for evidence_id in step.evidence_ids
        }
        referenced_ids.update(
            evidence_id
            for target in self.change_targets
            for evidence_id in target.evidence_ids
        )
        unknown_ids = sorted(referenced_ids - evidence_ids)
        if unknown_ids:
            raise ValueError(f"unknown evidence IDs: {unknown_ids}")
        return self


class ModelUsage(BaseModel):
    """Application-owned model usage and price telemetry for one model call."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    pricing_source: str = Field(default="unknown", min_length=1)
    pricing_version: str = Field(default="unknown", min_length=1)


class RagRunTrace(BaseModel):
    """Application-owned trace metadata for one direct-RAG run."""

    request_id: str = Field(min_length=1)
    session_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    started_at: datetime
    completed_at: datetime
    repository_id: str = Field(min_length=1)
    repository_name: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    question_mode: RagMode
    retrieval_mode: RetrievalMode
    retrieval_limit: int = Field(ge=1)
    retrieved_chunk_count: int = Field(ge=0)
    unique_file_count: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    latency_ms_total: int = Field(ge=0)
    latency_ms_retrieval: int = Field(ge=0)
    latency_ms_model: int | None = Field(default=None, ge=0)
    model_usage: list[ModelUsage] = Field(default_factory=list)
    total_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    insufficient_evidence: bool = False
    error_type: str | None = None
    error_message: str | None = None
    tool_call_count: int = Field(default=0, ge=0)
    graph_available: bool = False
    graph_expansion_count: int = Field(default=0, ge=0)
    graph_nodes_visited: int = Field(default=0, ge=0)
    graph_relationship_counts: dict[str, int] = Field(default_factory=dict)
    graph_fallback_reason: str | None = None
    answer_app_version: str | None = None
    answer_git_commit: str | None = None
    answer_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN


class RagRunResult(BaseModel):
    """A direct-RAG answer plus application-owned runtime trace metadata."""

    answer: RagAnswer
    trace: RagRunTrace


class ResearchRunResult(BaseModel):
    """An agentic-research answer plus application-owned runtime trace metadata."""

    answer: ResearchAnswer
    trace: RagRunTrace


class AnswerSnapshot(BaseModel):
    """Persisted answer payload used as input for later evaluation."""

    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    run_kind: RunKind
    question: str = Field(min_length=1)
    answer: RagAnswer | ResearchAnswer
    evidence: list[EvidenceItem] = Field(default_factory=list)
    repository_id: str = Field(min_length=1)
    repository_name: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    question_mode: RagMode
    retrieval_mode: RetrievalMode
    retrieval_limit: int = Field(ge=1)
    created_at: datetime
    answer_app_version: str | None = None
    answer_git_commit: str | None = None
    answer_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN


class EvaluatableAnswerSnapshot(AnswerSnapshot):
    """Persisted answer plus monitoring context needed by judge evaluation."""

    feedback_useful: int = Field(default=0, ge=0)
    feedback_not_useful: int = Field(default=0, ge=0)
    latency_ms_total: int | None = Field(default=None, ge=0)
    total_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)


class FeedbackRequest(BaseModel):
    """A user feedback submission for one browser session or returned run."""

    session_id: str | None = Field(default=None, min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    run_kind: RunKind | None = None
    useful: bool
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackEvent(BaseModel):
    """A persisted feedback event."""

    feedback_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    session_id: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    run_kind: RunKind | None = None
    useful: bool
    comment: str | None = Field(default=None, max_length=2000)
    submitted_at: datetime
    duplicate: bool = False


class RunKindCount(BaseModel):
    """Run count for one monitoring run kind."""

    run_kind: RunKind
    count: int = Field(ge=0)


class LatencyByRunKind(BaseModel):
    """Average latency for one monitoring run kind."""

    run_kind: RunKind
    average_latency_ms: float = Field(ge=0)


class RetrievalVolumeSummary(BaseModel):
    """Aggregate retrieval volume for monitoring dashboards."""

    retrieved_chunk_count: int = Field(default=0, ge=0)
    unique_file_count: int = Field(default=0, ge=0)


class ModelUsageSummary(BaseModel):
    """Aggregate token and cost telemetry for one model."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)


class FeedbackUsefulSummary(BaseModel):
    """Useful/not-useful feedback counts."""

    useful: int = Field(default=0, ge=0)
    not_useful: int = Field(default=0, ge=0)


class ErrorCountSummary(BaseModel):
    """Count of persisted run errors by error type."""

    error_type: str = Field(min_length=1)
    count: int = Field(ge=0)


class MonitoringSummary(BaseModel):
    """Backend aggregate data for reviewer-visible monitoring panels."""

    total_runs: int = Field(ge=0)
    runs_by_kind: list[RunKindCount] = Field(default_factory=list)
    average_latency_by_kind: list[LatencyByRunKind] = Field(default_factory=list)
    retrieval_volume: RetrievalVolumeSummary = Field(
        default_factory=RetrievalVolumeSummary
    )
    model_usage_by_model: list[ModelUsageSummary] = Field(default_factory=list)
    feedback: FeedbackUsefulSummary = Field(default_factory=FeedbackUsefulSummary)
    errors_by_type: list[ErrorCountSummary] = Field(default_factory=list)


class MonitoringFeedbackFilter(StrEnum):
    """Feedback filters supported by the monitoring run list."""

    ALL = "all"
    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    NONE = "none"


class MonitoringRunFeedback(BaseModel):
    """Feedback displayed in a monitoring run detail view."""

    feedback_id: str = Field(min_length=1)
    useful: bool
    comment: str | None = None
    submitted_at: datetime


class MonitoringRunSummary(BaseModel):
    """One persisted run row for the monitoring history table."""

    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    run_kind: RunKind
    started_at: datetime
    completed_at: datetime
    repository_name: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    question_mode: RagMode
    retrieval_mode: RetrievalMode
    retrieved_chunk_count: int = Field(ge=0)
    unique_file_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    latency_ms_total: int = Field(ge=0)
    latency_ms_retrieval: int = Field(ge=0)
    latency_ms_model: int | None = Field(default=None, ge=0)
    tool_call_count: int = Field(ge=0)
    insufficient_evidence: bool
    has_error: bool
    feedback_useful: int = Field(ge=0)
    feedback_not_useful: int = Field(ge=0)
    total_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    answer_app_version: str | None = None
    answer_git_commit: str | None = None
    answer_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN


class MonitoringRunDetail(MonitoringRunSummary):
    """Detailed persisted monitoring data for one run."""

    repository_id: str = Field(min_length=1)
    retrieval_limit: int = Field(ge=1)
    error_type: str | None = None
    error_message: str | None = None
    model_usage: list[ModelUsage] = Field(default_factory=list)
    feedback_events: list[MonitoringRunFeedback] = Field(default_factory=list)


class MonitoringRunList(BaseModel):
    """Recent persisted monitoring runs."""

    runs: list[MonitoringRunSummary] = Field(default_factory=list)


class EvaluationRecord(BaseModel):
    """One manually verified retrieval question and its expected evidence."""

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    relevant_files: list[str] = Field(min_length=1)
    relevant_symbols: list[str] = Field(default_factory=list)
    notes: str = ""


class EvaluationDatasetAudit(BaseModel):
    """Deterministic summary of versioned evaluation records."""

    dataset_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    question_type_counts: dict[str, int] = Field(default_factory=dict)


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


class RetrievalEvaluationSummary(EvaluationResult):
    """Persisted retrieval-evaluation metric row for dashboard highlights."""

    source_label: str = Field(min_length=1)
    selected: bool = False
    measured_at: datetime


class RetrievalEvaluationList(BaseModel):
    """Persisted retrieval-evaluation metrics for the dashboard."""

    results: list[RetrievalEvaluationSummary] = Field(default_factory=list)


class GroundTruthEvaluationSummary(BaseModel):
    """Persisted offline ground-truth answer assessment summary."""

    dataset: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    run_kind: RunKind
    record_count: int = Field(ge=0)
    answer_correctness: float | None = Field(default=None, ge=0, le=5)
    faithfulness: float = Field(ge=0, le=5)
    citation_precision: float = Field(ge=0, le=5)
    reference_coverage: float | None = Field(default=None, ge=0, le=5)
    answer_relevance: float = Field(ge=0, le=5)
    presentation_quality: float = Field(ge=0, le=5)
    unsupported_claim_count: int = Field(ge=0)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    average_latency_ms: float | None = Field(default=None, ge=0)
    total_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    measured_at: datetime


class GroundTruthEvaluationList(BaseModel):
    """Persisted offline ground-truth answer assessment summaries."""

    results: list[GroundTruthEvaluationSummary] = Field(default_factory=list)


class AnswerEvaluationResult(BaseModel):
    """LLM-judge scores for one grounded repository answer."""

    record_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer_correctness: float | None = Field(default=None, ge=0, le=5)
    faithfulness: float = Field(ge=0, le=5)
    citation_precision: float = Field(ge=0, le=5)
    reference_coverage: float | None = Field(default=None, ge=0, le=5)
    answer_relevance: float = Field(ge=0, le=5)
    presentation_quality: float = Field(ge=0, le=5)
    unsupported_claim_count: int = Field(ge=0)
    notes: str = ""


class EvaluationRunRecord(BaseModel):
    """Persisted metadata for one answer-evaluation batch."""

    evaluation_run_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    source_type: EvaluationSourceType
    source_label: str = Field(min_length=1)
    judge_model: str = Field(min_length=1)
    status: EvaluationRunStatus = EvaluationRunStatus.PENDING
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    evaluation_app_version: str | None = None
    evaluation_git_commit: str | None = None
    evaluation_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN


class PersistedEvaluationResult(BaseModel):
    """Persisted judge result linked to a dataset record or monitored answer."""

    evaluation_run_id: str = Field(min_length=1)
    result_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    record_id: str | None = Field(default=None, min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    run_kind: RunKind | None = None
    question: str = Field(min_length=1)
    answer_correctness: float | None = Field(default=None, ge=0, le=5)
    faithfulness: float = Field(ge=0, le=5)
    citation_precision: float = Field(ge=0, le=5)
    reference_coverage: float | None = Field(default=None, ge=0, le=5)
    answer_relevance: float = Field(ge=0, le=5)
    presentation_quality: float = Field(ge=0, le=5)
    unsupported_claim_count: int = Field(ge=0)
    feedback_useful: int = Field(default=0, ge=0)
    feedback_not_useful: int = Field(default=0, ge=0)
    latency_ms_total: int | None = Field(default=None, ge=0)
    total_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    graph_available: bool = False
    graph_expansion_count: int = Field(default=0, ge=0)
    graph_nodes_visited: int = Field(default=0, ge=0)
    graph_relationship_counts: dict[str, int] = Field(default_factory=dict)
    graph_fallback_reason: str | None = None
    notes: str = ""
    created_at: datetime


class EvaluationMetricAverage(BaseModel):
    """Average judge score for one answer-quality metric."""

    metric: str = Field(min_length=1)
    source_type: EvaluationSourceType | None = None
    average_score: float = Field(ge=0, le=5)
    result_count: int = Field(ge=0)


class EvaluationRunKindAverage(BaseModel):
    """Average answer-quality score for one answer approach."""

    run_kind: RunKind | None = None
    average_score: float = Field(ge=0, le=5)
    result_count: int = Field(ge=0)
    unsupported_claim_count: int = Field(ge=0)


class EvaluationDashboardSummary(BaseModel):
    """Aggregate answer-evaluation data for the browser dashboard."""

    total_runs: int = Field(ge=0)
    completed_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    total_results: int = Field(ge=0)
    average_score: float | None = Field(default=None, ge=0, le=5)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    average_by_run_kind: list[EvaluationRunKindAverage] = Field(default_factory=list)
    metric_averages: list[EvaluationMetricAverage] = Field(default_factory=list)


class EvaluationRunSummary(BaseModel):
    """One persisted answer-evaluation batch for the dashboard."""

    evaluation_run_id: str = Field(min_length=1)
    source_type: EvaluationSourceType
    source_label: str = Field(min_length=1)
    context_labels: list[str] = Field(default_factory=list)
    judge_model: str = Field(min_length=1)
    status: EvaluationRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    result_count: int = Field(ge=0)
    average_score: float | None = Field(default=None, ge=0, le=5)
    unsupported_claim_count: int = Field(ge=0)
    evaluation_app_version: str | None = None
    evaluation_git_commit: str | None = None
    evaluation_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN


class EvaluationRunList(BaseModel):
    """Recent persisted answer-evaluation runs."""

    runs: list[EvaluationRunSummary] = Field(default_factory=list)


class EvaluationResultSummary(BaseModel):
    """One persisted judged answer result for dashboard inspection."""

    result_id: str = Field(min_length=1)
    evaluation_run_id: str = Field(min_length=1)
    source_type: EvaluationSourceType
    source_label: str = Field(min_length=1)
    context_label: str = Field(min_length=1)
    repository_name: str | None = Field(default=None, min_length=1)
    branch: str | None = Field(default=None, min_length=1)
    commit_hash: str | None = Field(default=None, min_length=1)
    answer_app_version: str | None = None
    answer_git_commit: str | None = None
    answer_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN
    evaluation_app_version: str | None = None
    evaluation_git_commit: str | None = None
    evaluation_version_provenance: VersionProvenance = VersionProvenance.UNKNOWN
    record_id: str | None = Field(default=None, min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    run_kind: RunKind | None = None
    question: str = Field(min_length=1)
    answer_correctness: float | None = Field(default=None, ge=0, le=5)
    faithfulness: float = Field(ge=0, le=5)
    citation_precision: float = Field(ge=0, le=5)
    reference_coverage: float | None = Field(default=None, ge=0, le=5)
    answer_relevance: float = Field(ge=0, le=5)
    presentation_quality: float = Field(ge=0, le=5)
    average_score: float = Field(ge=0, le=5)
    unsupported_claim_count: int = Field(ge=0)
    feedback_useful: int = Field(ge=0)
    feedback_not_useful: int = Field(ge=0)
    latency_ms_total: int | None = Field(default=None, ge=0)
    total_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    graph_available: bool = False
    graph_expansion_count: int = Field(default=0, ge=0)
    graph_nodes_visited: int = Field(default=0, ge=0)
    graph_relationship_counts: dict[str, int] = Field(default_factory=dict)
    graph_fallback_reason: str | None = None
    notes: str = ""
    answer_evidence: list[EvidenceItem] = Field(default_factory=list)
    created_at: datetime


class EvaluationResultList(BaseModel):
    """Recent persisted judged answer results."""

    results: list[EvaluationResultSummary] = Field(default_factory=list)


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
    graph_nodes: int = Field(default=0, ge=0)
    graph_edges: int = Field(default=0, ge=0)
    graph_updated: bool = False
    graph_warning_count: int = Field(default=0, ge=0)
    graph_skipped_file_count: int = Field(default=0, ge=0)


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
