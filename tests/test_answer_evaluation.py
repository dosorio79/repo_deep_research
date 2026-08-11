"""Tests for unified answer-evaluation orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from repo_research.answer_evaluation import (
    audit_evaluation_records,
    dataset_candidates,
    judge_answer_candidates,
    monitored_answer_candidates,
    persist_evaluation_batch,
)
from repo_research.models import (
    AnswerEvaluationResult,
    EvaluatableAnswerSnapshot,
    EvaluationRecord,
    EvaluationRunRecord,
    EvaluationRunStatus,
    EvaluationSourceType,
    EvidenceItem,
    PersistedEvaluationResult,
    RagAnswer,
    RagMode,
    RagRequest,
    RagRunResult,
    RagRunTrace,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchRequest,
    ResearchRunResult,
    RetrievalMode,
    RunKind,
)


class FakeDirectService:
    """Return a direct answer run for dataset evaluation tests."""

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: RagRequest,
    ) -> RagRunResult:
        return RagRunResult(
            answer=_rag_answer(question=request.question, mode=request.mode),
            trace=_trace(
                repository=repository,
                run_kind=RunKind.DIRECT,
                request_id="direct-request",
                latency_ms_total=100,
            ),
        )


class FakeResearchService:
    """Return an agentic answer run for dataset evaluation tests."""

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: ResearchRequest,
    ) -> ResearchRunResult:
        return ResearchRunResult(
            answer=ResearchAnswer(
                question=request.question,
                mode=request.mode,
                summary="Agentic answer.",
                evidence=[_evidence()],
                relevant_files=["src/example.py"],
                relevant_symbols=["target"],
                confidence=0.8,
            ),
            trace=_trace(
                repository=repository,
                run_kind=RunKind.AGENTIC,
                request_id="agentic-request",
                latency_ms_total=250,
            ),
        )


class FakeJudge:
    """Return deterministic scores for direct and agentic answers."""

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: RagAnswer | ResearchAnswer,
        source_type: EvaluationSourceType = EvaluationSourceType.DATASET,
    ) -> AnswerEvaluationResult:
        answer_correctness = (
            None if source_type is EvaluationSourceType.MONITORED_RUNS else 4
        )
        reference_coverage = (
            None if source_type is EvaluationSourceType.MONITORED_RUNS else 4
        )
        return AnswerEvaluationResult(
            record_id=record.id,
            question=answer.question,
            answer_correctness=answer_correctness,
            faithfulness=5,
            citation_precision=5,
            reference_coverage=reference_coverage,
            answer_relevance=4,
            presentation_quality=4,
            unsupported_claim_count=0,
            notes=f"judged {type(answer).__name__}",
        )


class FakeMonitoredSource:
    """Return fixed monitored snapshots and capture filters."""

    def __init__(self, snapshots: list[EvaluatableAnswerSnapshot]) -> None:
        self.snapshots = snapshots
        self.calls: list[dict[str, object]] = []

    def list_answer_snapshots_for_evaluation(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        request_ids: list[str] | None = None,
    ) -> list[EvaluatableAnswerSnapshot]:
        self.calls.append(
            {
                "limit": limit,
                "run_kind": run_kind,
                "repository_name": repository_name,
                "request_ids": request_ids,
            }
        )
        return self.snapshots[:limit]


class FakeEvaluationStore:
    """Capture persisted evaluation lifecycle calls."""

    def __init__(self, *, fail_result: bool = False) -> None:
        self.fail_result = fail_result
        self.runs: list[EvaluationRunRecord] = []
        self.results: list[PersistedEvaluationResult] = []

    def record_evaluation_run(self, evaluation_run: EvaluationRunRecord) -> None:
        self.runs.append(evaluation_run)

    def record_evaluation_result(self, result: PersistedEvaluationResult) -> None:
        if self.fail_result:
            raise ValueError("postgres unavailable")
        self.results.append(result)


def test_dataset_audit_counts_records_and_question_types() -> None:
    records = [
        _record("locate_001", "locate"),
        _record("flow_001", "flow"),
        _record("change_001", "change"),
    ]

    audit = audit_evaluation_records({"development": records})

    assert audit.dataset_count == 1
    assert audit.record_count == 3
    assert audit.question_type_counts == {"change": 1, "flow": 1, "locate": 1}


def test_dataset_audit_rejects_duplicate_ids() -> None:
    records = [_record("locate_001", "locate"), _record("locate_001", "locate")]

    with pytest.raises(ValueError, match="duplicate evaluation record IDs"):
        audit_evaluation_records({"development": records})


def test_dataset_candidates_support_direct_and_agentic(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    records = [_record("change_001", "change")]

    candidates = dataset_candidates(
        direct_service=FakeDirectService(),
        research_service=FakeResearchService(),
        repository=repository,
        records=records,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT, RunKind.AGENTIC],
    )

    assert [candidate.run_kind for candidate in candidates] == [
        RunKind.DIRECT,
        RunKind.AGENTIC,
    ]
    assert candidates[0].request_id is None
    assert candidates[1].request_id is None
    assert candidates[0].latency_ms_total == 100
    assert candidates[1].latency_ms_total == 250
    assert candidates[1].answer.summary == "Agentic answer."


def test_monitored_answer_candidates_include_feedback_and_latency(
    tmp_path: Path,
) -> None:
    snapshot = EvaluatableAnswerSnapshot(
        request_id="request-1",
        session_id="session-1",
        run_kind=RunKind.AGENTIC,
        question="Which modules change?",
        answer=ResearchAnswer(
            question="Which modules change?",
            mode=RagMode.CHANGE,
            summary="Change src/example.py.",
            evidence=[_evidence()],
            confidence=0.8,
        ),
        evidence=[_evidence()],
        repository_id="repo-id",
        repository_name="repo",
        branch="main",
        commit_hash="abc123",
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.DENSE,
        retrieval_limit=5,
        created_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        feedback_useful=1,
        feedback_not_useful=2,
        latency_ms_total=1200,
        total_estimated_cost_usd=Decimal("0.012"),
    )
    source = FakeMonitoredSource([snapshot])

    candidates = monitored_answer_candidates(
        source=source,
        limit=10,
        run_kind=RunKind.AGENTIC,
        repository_name="repo",
        request_ids=["request-1", "request-2"],
    )

    assert source.calls == [
        {
            "limit": 10,
            "run_kind": RunKind.AGENTIC,
            "repository_name": "repo",
            "request_ids": ["request-1", "request-2"],
        }
    ]
    assert candidates[0].record.id == "request-1"
    assert candidates[0].feedback_useful == 1
    assert candidates[0].feedback_not_useful == 2
    assert candidates[0].latency_ms_total == 1200
    assert candidates[0].total_estimated_cost_usd == Decimal("0.012")


def test_judge_candidates_maps_scores_to_persisted_results(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    candidate = dataset_candidates(
        direct_service=FakeDirectService(),
        research_service=None,
        repository=repository,
        records=[_record("locate_001", "locate")],
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT],
    )[0]

    results = judge_answer_candidates(
        candidates=[candidate],
        judge=FakeJudge(),
        evaluation_run_id="eval-run-1",
    )

    assert results[0].evaluation_run_id == "eval-run-1"
    assert results[0].record_id == "locate_001"
    assert results[0].request_id is None
    assert results[0].run_kind is RunKind.DIRECT
    assert results[0].answer_correctness == 4
    assert results[0].reference_coverage == 4
    assert results[0].notes == "judged RagAnswer"


def test_judge_candidates_nulls_ground_truth_metrics_for_monitored_answers() -> None:
    snapshot = EvaluatableAnswerSnapshot(
        request_id="request-1",
        session_id="session-1",
        run_kind=RunKind.AGENTIC,
        question="Which modules change?",
        answer=ResearchAnswer(
            question="Which modules change?",
            mode=RagMode.CHANGE,
            summary="Change src/example.py.",
            evidence=[_evidence()],
            confidence=0.8,
        ),
        evidence=[_evidence()],
        repository_id="repo-id",
        repository_name="repo",
        branch="main",
        commit_hash="abc123",
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.DENSE,
        retrieval_limit=5,
        created_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )
    candidate = monitored_answer_candidates(
        source=FakeMonitoredSource([snapshot]),
        limit=1,
    )[0]

    results = judge_answer_candidates(
        candidates=[candidate],
        judge=FakeJudge(),
        evaluation_run_id="eval-run-1",
    )

    assert results[0].request_id == "request-1"
    assert results[0].answer_correctness is None
    assert results[0].reference_coverage is None
    assert results[0].faithfulness == 5


def test_persist_evaluation_batch_records_running_results_and_completed() -> None:
    store = FakeEvaluationStore()
    evaluation_run = EvaluationRunRecord(
        evaluation_run_id="eval-run-1",
        source_type=EvaluationSourceType.DATASET,
        source_label="eval/development.json",
        judge_model="gpt-5.1",
        started_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )
    result = PersistedEvaluationResult(
        evaluation_run_id="eval-run-1",
        record_id="locate_001",
        request_id="request-1",
        run_kind=RunKind.DIRECT,
        question="Where is target?",
        answer_correctness=4,
        faithfulness=5,
        citation_precision=5,
        reference_coverage=4,
        answer_relevance=4,
        presentation_quality=4,
        unsupported_claim_count=0,
        created_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )

    completed = persist_evaluation_batch(
        store=store,
        evaluation_run=evaluation_run,
        results=[result],
    )

    assert [run.status for run in store.runs] == [
        EvaluationRunStatus.RUNNING,
        EvaluationRunStatus.COMPLETED,
    ]
    assert store.results == [result]
    assert completed.status is EvaluationRunStatus.COMPLETED
    assert completed.completed_at is not None


def test_persist_evaluation_batch_marks_failed_when_result_write_fails() -> None:
    store = FakeEvaluationStore(fail_result=True)
    evaluation_run = EvaluationRunRecord(
        evaluation_run_id="eval-run-1",
        source_type=EvaluationSourceType.DATASET,
        source_label="eval/development.json",
        judge_model="gpt-5.1",
        started_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )
    result = PersistedEvaluationResult(
        evaluation_run_id="eval-run-1",
        record_id="locate_001",
        request_id="request-1",
        run_kind=RunKind.DIRECT,
        question="Where is target?",
        answer_correctness=4,
        faithfulness=5,
        citation_precision=5,
        reference_coverage=4,
        answer_relevance=4,
        presentation_quality=4,
        unsupported_claim_count=0,
        created_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="postgres unavailable"):
        persist_evaluation_batch(
            store=store,
            evaluation_run=evaluation_run,
            results=[result],
        )

    assert [run.status for run in store.runs] == [
        EvaluationRunStatus.RUNNING,
        EvaluationRunStatus.FAILED,
    ]
    assert store.runs[-1].error_message == "postgres unavailable"


def _record(record_id: str, question_type: str) -> EvaluationRecord:
    return EvaluationRecord(
        id=record_id,
        question="Where is target?",
        question_type=question_type,
        relevant_files=["src/example.py"],
        relevant_symbols=["target"],
    )


def _repository(root: Path) -> RepositoryIdentity:
    return RepositoryIdentity(
        name="sample",
        root_path=root,
        branch="main",
        commit_hash="abc123",
    )


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="E1",
        path="src/example.py",
        start_line=1,
        end_line=3,
        symbol="target",
        score=0.9,
        reason="Relevant evidence.",
    )


def _rag_answer(*, question: str, mode: RagMode) -> RagAnswer:
    return RagAnswer(
        question=question,
        mode=mode,
        summary="Direct answer.",
        evidence=[_evidence()],
        relevant_files=["src/example.py"],
        relevant_symbols=["target"],
        confidence=0.8,
    )


def _trace(
    *,
    repository: RepositoryIdentity,
    run_kind: RunKind,
    request_id: str,
    latency_ms_total: int,
) -> RagRunTrace:
    return RagRunTrace(
        request_id=request_id,
        session_id="session-1",
        started_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        completed_at=datetime(2026, 8, 11, 12, 0, 1, tzinfo=UTC),
        repository_id=repository.repository_id,
        repository_name=repository.name,
        branch=repository.branch,
        commit_hash=repository.commit_hash,
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.DENSE,
        retrieval_limit=5,
        retrieved_chunk_count=1,
        unique_file_count=1,
        evidence_ids=["E1"],
        latency_ms_total=latency_ms_total,
        latency_ms_retrieval=10,
        tool_call_count=2 if run_kind is RunKind.AGENTIC else 0,
    )
