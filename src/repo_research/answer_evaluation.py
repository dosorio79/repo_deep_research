"""Unified answer-quality evaluation for datasets and monitored answers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from repo_research.evaluation import load_records
from repo_research.models import (
    AnswerEvaluationResult,
    EvaluatableAnswerSnapshot,
    EvaluationDatasetAudit,
    EvaluationRecord,
    EvaluationRunRecord,
    EvaluationRunStatus,
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
) -> list[AnswerEvaluationCandidate]:
    """Generate answer candidates from curated records."""
    candidates: list[AnswerEvaluationCandidate] = []
    for approach in approaches:
        for record in records:
            mode = _rag_mode_from_question_type(record.question_type)
            if approach is RunKind.DIRECT:
                direct_run = direct_service.run(
                    repository=repository,
                    request=RagRequest(
                        question=record.question,
                        mode=mode,
                        retrieval_mode=retrieval_mode,
                        limit=limit,
                    ),
                )
                candidates.append(
                    AnswerEvaluationCandidate(
                        record=record,
                        answer=direct_run.answer,
                        run_kind=RunKind.DIRECT,
                        latency_ms_total=direct_run.trace.latency_ms_total,
                        total_estimated_cost_usd=(
                            direct_run.trace.total_estimated_cost_usd
                        ),
                    )
                )
                continue
            if research_service is None:
                raise ValueError("agentic evaluation requires a research service")
            research_run = research_service.run(
                repository=repository,
                request=ResearchRequest(
                    question=record.question,
                    mode=mode,
                    retrieval_mode=retrieval_mode,
                    retrieval_limit=limit,
                ),
            )
            candidates.append(
                AnswerEvaluationCandidate(
                    record=record,
                    answer=research_run.answer,
                    run_kind=RunKind.AGENTIC,
                    latency_ms_total=research_run.trace.latency_ms_total,
                    total_estimated_cost_usd=(
                        research_run.trace.total_estimated_cost_usd
                    ),
                )
            )
    return candidates


def monitored_answer_candidates(
    *,
    source: MonitoredAnswerSource,
    limit: int,
    run_kind: RunKind | None = None,
    repository_name: str | None = None,
) -> list[AnswerEvaluationCandidate]:
    """Load answer candidates from persisted monitoring snapshots."""
    snapshots = source.list_answer_snapshots_for_evaluation(
        limit=limit,
        run_kind=run_kind,
        repository_name=repository_name,
    )
    return [
        AnswerEvaluationCandidate(
            record=_record_from_snapshot(snapshot),
            answer=snapshot.answer,
            run_kind=snapshot.run_kind,
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
) -> list[PersistedEvaluationResult]:
    """Judge candidates and map scores to persisted result records."""
    created_at = datetime.now(UTC)
    results: list[PersistedEvaluationResult] = []
    for candidate in candidates:
        judged = judge.judge_answer(record=candidate.record, answer=candidate.answer)
        results.append(
            _persisted_result_from_judgement(
                candidate=candidate,
                judgement=judged,
                evaluation_run_id=evaluation_run_id,
                created_at=created_at,
            )
        )
    return results


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
        correctness=judgement.correctness,
        groundedness=judgement.groundedness,
        citation_accuracy=judgement.citation_accuracy,
        completeness=judgement.completeness,
        usefulness=judgement.usefulness,
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
