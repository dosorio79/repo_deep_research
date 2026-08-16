"""Unified answer-quality evaluation for datasets and monitored answers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, TypeVar

from repo_research.evaluation import load_records
from repo_research.models import (
    AnswerEvaluationResult,
    EvaluatableAnswerSnapshot,
    EvaluationDatasetAudit,
    EvaluationRecord,
    EvaluationRunRecord,
    EvaluationRunStatus,
    EvaluationSourceType,
    PersistedEvaluationResult,
    RagAnswer,
    RagMode,
    RagRequest,
    RagRunResult,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchRequest,
    ResearchRunResult,
    RetrievalMode,
    RunKind,
)
from repo_research.rag import AnswerJudge

T = TypeVar("T")
U = TypeVar("U")


class EvaluationRecordingStore(Protocol):
    """Persistence behavior required by the answer evaluation runner."""

    def record_evaluation_run(self, evaluation_run: EvaluationRunRecord) -> None:
        """Persist evaluation-run lifecycle state."""

    def record_evaluation_result(self, result: PersistedEvaluationResult) -> None:
        """Persist one judged answer result."""


class MonitoredAnswerSource(Protocol):
    """Read behavior required to evaluate monitored answers."""

    def list_answer_snapshots_for_evaluation(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        request_ids: list[str] | None = None,
    ) -> list[EvaluatableAnswerSnapshot]:
        """Return recent monitored answer snapshots."""


class DirectAnswerService(Protocol):
    """Direct-RAG behavior required by dataset evaluation."""

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: RagRequest,
    ) -> RagRunResult:
        """Return an object with answer and trace fields."""


class ResearchAnswerService(Protocol):
    """Agentic research behavior required by dataset evaluation."""

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: ResearchRequest,
    ) -> ResearchRunResult:
        """Return an agentic answer run."""


@dataclass(frozen=True)
class AnswerEvaluationCandidate:
    """One answer ready for judge scoring and optional persistence."""

    record: EvaluationRecord
    answer: RagAnswer | ResearchAnswer
    run_kind: RunKind
    source_type: EvaluationSourceType = EvaluationSourceType.DATASET
    request_id: str | None = None
    feedback_useful: int = 0
    feedback_not_useful: int = 0
    latency_ms_total: int | None = None
    total_estimated_cost_usd: Decimal | None = None


def audit_evaluation_records(
    datasets: Mapping[str, list[EvaluationRecord]],
) -> EvaluationDatasetAudit:
    """Return deterministic record counts for capstone evaluation evidence."""
    question_type_counts: dict[str, int] = {}
    record_count = 0
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for records in datasets.values():
        for record in records:
            record_count += 1
            if record.id in seen_ids:
                duplicate_ids.add(record.id)
            seen_ids.add(record.id)
            question_type_counts[record.question_type] = (
                question_type_counts.get(record.question_type, 0) + 1
            )
    if duplicate_ids:
        raise ValueError(f"duplicate evaluation record IDs: {sorted(duplicate_ids)}")
    return EvaluationDatasetAudit(
        dataset_count=len(datasets),
        record_count=record_count,
        question_type_counts=dict(sorted(question_type_counts.items())),
    )


def dataset_candidates(
    *,
    direct_service: DirectAnswerService,
    research_service: ResearchAnswerService | None,
    repository: RepositoryIdentity,
    records: list[EvaluationRecord],
    retrieval_mode: RetrievalMode,
    limit: int,
    approaches: Iterable[RunKind],
    workers: int = 1,
) -> list[AnswerEvaluationCandidate]:
    """Generate answer candidates from curated records."""
    candidates: list[AnswerEvaluationCandidate] = []

    def direct_candidate(record: EvaluationRecord) -> AnswerEvaluationCandidate:
        mode = _rag_mode_from_question_type(record.question_type)
        direct_run = direct_service.run(
            repository=repository,
            request=RagRequest(
                question=record.question,
                mode=mode,
                retrieval_mode=retrieval_mode,
                limit=limit,
            ),
        )
        return AnswerEvaluationCandidate(
            record=record,
            answer=direct_run.answer,
            run_kind=RunKind.DIRECT,
            source_type=EvaluationSourceType.DATASET,
            latency_ms_total=direct_run.trace.latency_ms_total,
            total_estimated_cost_usd=direct_run.trace.total_estimated_cost_usd,
        )

    def agentic_candidate(record: EvaluationRecord) -> AnswerEvaluationCandidate:
        mode = _rag_mode_from_question_type(record.question_type)
        assert research_service is not None
        research_run = research_service.run(
            repository=repository,
            request=ResearchRequest(
                question=record.question,
                mode=mode,
                retrieval_mode=retrieval_mode,
                retrieval_limit=limit,
            ),
        )
        return AnswerEvaluationCandidate(
            record=record,
            answer=research_run.answer,
            run_kind=RunKind.AGENTIC,
            source_type=EvaluationSourceType.DATASET,
            latency_ms_total=research_run.trace.latency_ms_total,
            total_estimated_cost_usd=research_run.trace.total_estimated_cost_usd,
        )

    for approach in approaches:
        if approach is RunKind.DIRECT:
            candidates.extend(_map_stably(direct_candidate, records, workers=workers))
            continue
        if research_service is None:
            raise ValueError("agentic evaluation requires a research service")
        candidates.extend(_map_stably(agentic_candidate, records, workers=1))
    return candidates


def monitored_answer_candidates(
    *,
    source: MonitoredAnswerSource,
    limit: int,
    run_kind: RunKind | None = None,
    repository_name: str | None = None,
    request_ids: list[str] | None = None,
) -> list[AnswerEvaluationCandidate]:
    """Load answer candidates from persisted monitoring snapshots."""
    snapshots = source.list_answer_snapshots_for_evaluation(
        limit=limit,
        run_kind=run_kind,
        repository_name=repository_name,
        request_ids=request_ids,
    )
    return [
        AnswerEvaluationCandidate(
            record=_record_from_snapshot(snapshot),
            answer=snapshot.answer,
            run_kind=snapshot.run_kind,
            source_type=EvaluationSourceType.MONITORED_RUNS,
            request_id=snapshot.request_id,
            feedback_useful=snapshot.feedback_useful,
            feedback_not_useful=snapshot.feedback_not_useful,
            latency_ms_total=snapshot.latency_ms_total,
            total_estimated_cost_usd=snapshot.total_estimated_cost_usd,
        )
        for snapshot in snapshots
    ]


def judge_answer_candidates(
    *,
    candidates: list[AnswerEvaluationCandidate],
    judge: AnswerJudge,
    evaluation_run_id: str,
    workers: int = 1,
) -> list[PersistedEvaluationResult]:
    """Judge candidates and map scores to persisted result records."""
    created_at = datetime.now(UTC)

    def result_for(candidate: AnswerEvaluationCandidate) -> PersistedEvaluationResult:
        return _judge_candidate(
            candidate=candidate,
            judge=judge,
            evaluation_run_id=evaluation_run_id,
            created_at=created_at,
        )

    return _map_stably(result_for, candidates, workers=workers)


def evaluate_dataset_answer_candidates(
    *,
    direct_service: DirectAnswerService,
    research_service: ResearchAnswerService | None,
    judge: AnswerJudge,
    repository: RepositoryIdentity,
    records: list[EvaluationRecord],
    retrieval_mode: RetrievalMode,
    limit: int,
    approaches: Iterable[RunKind],
    evaluation_run_id: str,
    workers: int = 1,
    checkpoint_path: Path | None = None,
) -> list[PersistedEvaluationResult]:
    """Generate, judge, and checkpoint dataset answer results."""
    approach_list = list(approaches)
    expected_keys = [
        (record.id, approach) for approach in approach_list for record in records
    ]
    results_by_key = _load_checkpointed_results(
        checkpoint_path=checkpoint_path,
        evaluation_run_id=evaluation_run_id,
    )

    def evaluate_record(
        task: tuple[RunKind, EvaluationRecord],
    ) -> PersistedEvaluationResult:
        approach, record = task
        candidates = dataset_candidates(
            direct_service=direct_service,
            research_service=research_service,
            repository=repository,
            records=[record],
            retrieval_mode=retrieval_mode,
            limit=limit,
            approaches=[approach],
            workers=1,
        )
        return _judge_candidate(
            candidate=candidates[0],
            judge=judge,
            evaluation_run_id=evaluation_run_id,
            created_at=datetime.now(UTC),
        )

    for approach in approach_list:
        pending_tasks = [
            (approach, record)
            for record in records
            if (record.id, approach) not in results_by_key
        ]
        if not pending_tasks:
            continue
        approach_workers = workers if approach is RunKind.DIRECT else 1
        for result in _iter_map_stably(
            evaluate_record, pending_tasks, workers=approach_workers
        ):
            results_by_key[_result_key(result)] = result
            _append_checkpoint_result(checkpoint_path=checkpoint_path, result=result)

    return [results_by_key[key] for key in expected_keys if key in results_by_key]


def persist_evaluation_batch(
    *,
    store: EvaluationRecordingStore,
    evaluation_run: EvaluationRunRecord,
    results: list[PersistedEvaluationResult],
) -> EvaluationRunRecord:
    """Persist run lifecycle and judged answer results."""
    running = evaluation_run.model_copy(update={"status": EvaluationRunStatus.RUNNING})
    store.record_evaluation_run(running)
    try:
        for result in results:
            store.record_evaluation_result(result)
    except Exception as error:
        failed = running.model_copy(
            update={
                "status": EvaluationRunStatus.FAILED,
                "completed_at": datetime.now(UTC),
                "error_message": str(error),
            }
        )
        store.record_evaluation_run(failed)
        raise
    completed = running.model_copy(
        update={
            "status": EvaluationRunStatus.COMPLETED,
            "completed_at": datetime.now(UTC),
            "error_message": None,
        }
    )
    store.record_evaluation_run(completed)
    return completed


def write_persisted_answer_evaluation_report(
    results: list[PersistedEvaluationResult], path: Path
) -> None:
    """Write stable JSON output for unified answer evaluation results."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([result.model_dump(mode="json") for result in results], indent=2)
        + "\n",
        encoding="utf-8",
    )


def load_and_audit_records(
    paths: Iterable[Path],
) -> tuple[list[EvaluationRecord], EvaluationDatasetAudit]:
    """Load datasets and return records plus a combined audit summary."""
    datasets = {path.as_posix(): load_records(path) for path in paths}
    records = [
        record for dataset_records in datasets.values() for record in dataset_records
    ]
    return records, audit_evaluation_records(datasets)


def _record_from_snapshot(snapshot: EvaluatableAnswerSnapshot) -> EvaluationRecord:
    answer_paths = sorted({item.path for item in snapshot.answer.evidence})
    answer_symbols = sorted(
        {item.symbol for item in snapshot.answer.evidence if item.symbol}
    )
    return EvaluationRecord(
        id=snapshot.request_id,
        question=snapshot.question,
        question_type=snapshot.question_mode.value,
        relevant_files=answer_paths or ["monitored-answer-without-citations"],
        relevant_symbols=answer_symbols,
        notes=(
            "Monitored answer evaluation uses returned citations as the available "
            "grounding record; it is not a manually verified ground-truth item."
        ),
    )


def _judge_candidate(
    *,
    candidate: AnswerEvaluationCandidate,
    judge: AnswerJudge,
    evaluation_run_id: str,
    created_at: datetime,
) -> PersistedEvaluationResult:
    judged = judge.judge_answer(
        record=candidate.record,
        answer=candidate.answer,
        source_type=candidate.source_type,
    )
    return _persisted_result_from_judgement(
        candidate=candidate,
        judgement=judged,
        evaluation_run_id=evaluation_run_id,
        created_at=created_at,
    )


def _persisted_result_from_judgement(
    *,
    candidate: AnswerEvaluationCandidate,
    judgement: AnswerEvaluationResult,
    evaluation_run_id: str,
    created_at: datetime,
) -> PersistedEvaluationResult:
    return PersistedEvaluationResult(
        evaluation_run_id=evaluation_run_id,
        record_id=judgement.record_id,
        request_id=candidate.request_id,
        run_kind=candidate.run_kind,
        question=judgement.question,
        answer_correctness=(
            None
            if candidate.source_type is EvaluationSourceType.MONITORED_RUNS
            else judgement.answer_correctness
        ),
        faithfulness=judgement.faithfulness,
        citation_precision=judgement.citation_precision,
        reference_coverage=(
            None
            if candidate.source_type is EvaluationSourceType.MONITORED_RUNS
            else judgement.reference_coverage
        ),
        answer_relevance=judgement.answer_relevance,
        presentation_quality=judgement.presentation_quality,
        unsupported_claim_count=judgement.unsupported_claim_count,
        feedback_useful=candidate.feedback_useful,
        feedback_not_useful=candidate.feedback_not_useful,
        latency_ms_total=candidate.latency_ms_total,
        total_estimated_cost_usd=candidate.total_estimated_cost_usd,
        notes=judgement.notes,
        created_at=created_at,
    )


def _rag_mode_from_question_type(question_type: str) -> RagMode:
    mapping = {
        "locate": RagMode.LOCATE,
        "flow": RagMode.FLOW,
        "change": RagMode.CHANGE,
    }
    return mapping.get(question_type, RagMode.AUTO)


def _load_checkpointed_results(
    *,
    checkpoint_path: Path | None,
    evaluation_run_id: str,
) -> dict[tuple[str, RunKind], PersistedEvaluationResult]:
    if checkpoint_path is None or not checkpoint_path.exists():
        return {}
    results: dict[tuple[str, RunKind], PersistedEvaluationResult] = {}
    for raw_line in checkpoint_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        result = PersistedEvaluationResult.model_validate_json(raw_line).model_copy(
            update={"evaluation_run_id": evaluation_run_id}
        )
        results[_result_key(result)] = result
    return results


def _append_checkpoint_result(
    *,
    checkpoint_path: Path | None,
    result: PersistedEvaluationResult,
) -> None:
    if checkpoint_path is None:
        return
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as handle:
        handle.write(result.model_dump_json() + "\n")


def _result_key(result: PersistedEvaluationResult) -> tuple[str, RunKind]:
    if result.record_id is None or result.run_kind is None:
        raise ValueError(
            "dataset evaluation checkpoints require record_id and run_kind"
        )
    return result.record_id, result.run_kind


def _map_stably(
    func: Callable[[T], U],
    items: list[T],
    *,
    workers: int,
) -> list[U]:
    return list(_iter_map_stably(func, items, workers=workers))


def _iter_map_stably(
    func: Callable[[T], U],
    items: list[T],
    *,
    workers: int,
) -> Iterable[U]:
    if workers <= 1 or len(items) <= 1:
        for item in items:
            yield func(item)
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as executor:
        yield from executor.map(func, items)
