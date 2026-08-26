"""Tests for unified answer-evaluation orchestration."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock

import pytest

from repo_research.answer_evaluation import (
    audit_evaluation_records,
    dataset_candidates,
    evaluate_dataset_answer_candidates,
    judge_answer_candidates,
    monitored_answer_candidates,
    persist_evaluation_batch,
    summarize_ground_truth_evaluation_results,
)
from repo_research.models import (
    AnswerEvaluationResult,
    EvaluatableAnswerSnapshot,
    EvaluationRecord,
    EvaluationRunRecord,
    EvaluationRunStatus,
    EvaluationSourceType,
    EvidenceItem,
    GroundTruthEvaluationSummary,
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

    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.active_calls = 0
        self.max_active_calls = 0
        self._lock = Lock()

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: RagRequest,
    ) -> RagRunResult:
        with self._lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
            return RagRunResult(
                answer=_rag_answer(question=request.question, mode=request.mode),
                trace=_trace(
                    repository=repository,
                    run_kind=RunKind.DIRECT,
                    request_id="direct-request",
                    latency_ms_total=100,
                ),
            )
        finally:
            with self._lock:
                self.active_calls -= 1


class FakeResearchService:
    """Return an agentic answer run for dataset evaluation tests."""

    def __init__(
        self, *, delay_seconds: float = 0.0, fail_on_call: int | None = None
    ) -> None:
        self.delay_seconds = delay_seconds
        self.fail_on_call = fail_on_call
        self.call_count = 0
        self.active_calls = 0
        self.max_active_calls = 0
        self._lock = Lock()

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: ResearchRequest,
    ) -> ResearchRunResult:
        with self._lock:
            self.call_count += 1
            call_count = self.call_count
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if self.fail_on_call == call_count:
                raise ValueError(f"research failed on call {call_count}")
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
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
        finally:
            with self._lock:
                self.active_calls -= 1


class FakeJudge:
    """Return deterministic scores for direct and agentic answers."""

    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        fail_record_ids: set[str] | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.fail_record_ids = fail_record_ids or set()

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: RagAnswer | ResearchAnswer,
        source_type: EvaluationSourceType = EvaluationSourceType.DATASET,
    ) -> AnswerEvaluationResult:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if record.id in self.fail_record_ids:
            raise ValueError(f"judge failed for {record.id}")
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
        unevaluated_only: bool = False,
    ) -> list[EvaluatableAnswerSnapshot]:
        self.calls.append(
            {
                "limit": limit,
                "run_kind": run_kind,
                "repository_name": repository_name,
                "request_ids": request_ids,
                "unevaluated_only": unevaluated_only,
            }
        )
        return self.snapshots[:limit]


class FakeEvaluationStore:
    """Capture persisted evaluation lifecycle calls."""

    def __init__(self, *, fail_result: bool = False) -> None:
        self.fail_result = fail_result
        self.runs: list[EvaluationRunRecord] = []
        self.results: list[PersistedEvaluationResult] = []
        self.ground_truth_results: list[GroundTruthEvaluationSummary] = []

    def record_evaluation_run(self, evaluation_run: EvaluationRunRecord) -> None:
        self.runs.append(evaluation_run)

    def record_evaluation_result(self, result: PersistedEvaluationResult) -> None:
        if self.fail_result:
            raise ValueError("postgres unavailable")
        self.results.append(result)

    def record_ground_truth_evaluation_result(
        self, result: GroundTruthEvaluationSummary
    ) -> None:
        self.ground_truth_results.append(result)


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


def test_dataset_candidates_parallel_workers_preserve_stable_order(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    records = [
        _record("locate_001", "locate"),
        _record("flow_001", "flow"),
        _record("change_001", "change"),
    ]
    direct_service = FakeDirectService(delay_seconds=0.05)

    candidates = dataset_candidates(
        direct_service=direct_service,
        research_service=FakeResearchService(),
        repository=repository,
        records=records,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT],
        workers=3,
    )

    assert direct_service.max_active_calls > 1
    assert [candidate.record.id for candidate in candidates] == [
        "locate_001",
        "flow_001",
        "change_001",
    ]


def test_dataset_candidates_serializes_agentic_generation_with_shared_service(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    records = [
        _record("locate_001", "locate"),
        _record("flow_001", "flow"),
        _record("change_001", "change"),
    ]
    research_service = FakeResearchService(delay_seconds=0.05)

    candidates = dataset_candidates(
        direct_service=FakeDirectService(),
        research_service=research_service,
        repository=repository,
        records=records,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.AGENTIC],
        workers=3,
    )

    assert [candidate.record.id for candidate in candidates] == [
        "locate_001",
        "flow_001",
        "change_001",
    ]
    assert research_service.max_active_calls == 1


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
            "unevaluated_only": False,
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


def test_judge_candidates_parallel_workers_preserve_stable_order(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    candidates = dataset_candidates(
        direct_service=FakeDirectService(),
        research_service=None,
        repository=repository,
        records=[
            _record("locate_001", "locate"),
            _record("flow_001", "flow"),
            _record("change_001", "change"),
        ],
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT],
    )
    started = time.perf_counter()

    results = judge_answer_candidates(
        candidates=candidates,
        judge=FakeJudge(delay_seconds=0.05),
        evaluation_run_id="eval-run-1",
        workers=3,
    )

    assert time.perf_counter() - started < 0.14
    assert [result.record_id for result in results] == [
        "locate_001",
        "flow_001",
        "change_001",
    ]


def test_dataset_answer_evaluation_checkpoints_each_judged_result(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    records = [_record("locate_001", "locate"), _record("flow_001", "flow")]
    checkpoint_path = tmp_path / "answer-held-out-both.jsonl"

    with pytest.raises(ValueError, match="judge failed for flow_001"):
        evaluate_dataset_answer_candidates(
            direct_service=FakeDirectService(),
            research_service=None,
            judge=FakeJudge(fail_record_ids={"flow_001"}),
            repository=repository,
            records=records,
            retrieval_mode=RetrievalMode.DENSE,
            limit=5,
            approaches=[RunKind.DIRECT],
            evaluation_run_id="eval-run-1",
            workers=1,
            checkpoint_path=checkpoint_path,
            checkpoint_context="dataset-a-dense",
        )

    assert checkpoint_path.read_text(encoding="utf-8").count("\n") == 2
    assert "# context:dataset-a-dense" in checkpoint_path.read_text(encoding="utf-8")
    assert "locate_001" in checkpoint_path.read_text(encoding="utf-8")

    results = evaluate_dataset_answer_candidates(
        direct_service=FakeDirectService(),
        research_service=None,
        judge=FakeJudge(),
        repository=repository,
        records=records,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT],
        evaluation_run_id="eval-run-2",
        workers=1,
        checkpoint_path=checkpoint_path,
        checkpoint_context="dataset-a-dense",
    )

    assert [result.record_id for result in results] == ["locate_001", "flow_001"]
    assert {result.evaluation_run_id for result in results} == {"eval-run-2"}
    assert checkpoint_path.read_text(encoding="utf-8").count("\n") == 3


def test_dataset_answer_evaluation_rejects_mismatched_checkpoint_context(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    records = [_record("locate_001", "locate")]
    checkpoint_path = tmp_path / "answer-held-out-both.jsonl"
    evaluate_dataset_answer_candidates(
        direct_service=FakeDirectService(),
        research_service=None,
        judge=FakeJudge(),
        repository=repository,
        records=records,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT],
        evaluation_run_id="eval-run-1",
        workers=1,
        checkpoint_path=checkpoint_path,
        checkpoint_context="dataset-a-dense",
    )

    with pytest.raises(ValueError, match="different evaluation context"):
        evaluate_dataset_answer_candidates(
            direct_service=FakeDirectService(),
            research_service=None,
            judge=FakeJudge(),
            repository=repository,
            records=records,
            retrieval_mode=RetrievalMode.HYBRID,
            limit=5,
            approaches=[RunKind.DIRECT],
            evaluation_run_id="eval-run-2",
            workers=1,
            checkpoint_path=checkpoint_path,
            checkpoint_context="dataset-a-hybrid",
        )


def test_dataset_answer_evaluation_checkpoints_agentic_before_later_failure(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    records = [_record("locate_001", "locate"), _record("flow_001", "flow")]
    checkpoint_path = tmp_path / "answer-held-out-both.jsonl"

    with pytest.raises(ValueError, match="research failed on call 2"):
        evaluate_dataset_answer_candidates(
            direct_service=FakeDirectService(),
            research_service=FakeResearchService(fail_on_call=2),
            judge=FakeJudge(),
            repository=repository,
            records=records,
            retrieval_mode=RetrievalMode.DENSE,
            limit=5,
            approaches=[RunKind.AGENTIC],
            evaluation_run_id="eval-run-1",
            workers=6,
            checkpoint_path=checkpoint_path,
        )

    assert checkpoint_path.read_text(encoding="utf-8").count("\n") == 1
    assert "locate_001" in checkpoint_path.read_text(encoding="utf-8")


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


def test_summarize_ground_truth_evaluation_results_groups_dataset_metrics() -> None:
    measured_at = datetime(2026, 8, 16, 10, tzinfo=UTC)
    results = [
        PersistedEvaluationResult(
            evaluation_run_id="eval-run-1",
            record_id="locate_001",
            run_kind=RunKind.DIRECT,
            question="Where is target?",
            answer_correctness=4,
            faithfulness=5,
            citation_precision=5,
            reference_coverage=3,
            answer_relevance=4,
            presentation_quality=5,
            unsupported_claim_count=0,
            latency_ms_total=1000,
            total_estimated_cost_usd=Decimal("0.010"),
            created_at=measured_at,
        ),
        PersistedEvaluationResult(
            evaluation_run_id="eval-run-1",
            record_id="flow_001",
            run_kind=RunKind.DIRECT,
            question="How does target flow?",
            answer_correctness=2,
            faithfulness=3,
            citation_precision=4,
            reference_coverage=1,
            answer_relevance=4,
            presentation_quality=3,
            unsupported_claim_count=2,
            latency_ms_total=3000,
            total_estimated_cost_usd=Decimal("0.015"),
            created_at=measured_at,
        ),
        PersistedEvaluationResult(
            evaluation_run_id="eval-run-1",
            record_id="locate_001",
            run_kind=RunKind.AGENTIC,
            question="Where is target?",
            answer_correctness=5,
            faithfulness=5,
            citation_precision=5,
            reference_coverage=4,
            answer_relevance=5,
            presentation_quality=4,
            unsupported_claim_count=1,
            latency_ms_total=None,
            total_estimated_cost_usd=None,
            created_at=measured_at,
        ),
        PersistedEvaluationResult(
            evaluation_run_id="eval-run-2",
            request_id="request-1",
            run_kind=RunKind.DIRECT,
            question="Live answer?",
            answer_correctness=None,
            faithfulness=5,
            citation_precision=5,
            reference_coverage=None,
            answer_relevance=5,
            presentation_quality=5,
            unsupported_claim_count=0,
            created_at=measured_at,
        ),
    ]

    summaries = summarize_ground_truth_evaluation_results(
        results,
        dataset="eval/held_out.json",
        source_label="held-out answer evaluation",
        measured_at=measured_at,
    )

    direct = next(item for item in summaries if item.run_kind is RunKind.DIRECT)
    agentic = next(item for item in summaries if item.run_kind is RunKind.AGENTIC)
    assert direct.record_count == 2
    assert direct.answer_correctness == 3
    assert direct.faithfulness == 4
    assert direct.unsupported_claim_count == 2
    assert direct.unsupported_claim_rate == 0.5
    assert direct.average_latency_ms == 2000
    assert direct.total_estimated_cost_usd == Decimal("0.025")
    assert agentic.record_count == 1
    assert agentic.average_latency_ms is None
    assert agentic.total_estimated_cost_usd is None


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
