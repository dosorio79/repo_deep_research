"""PostgreSQL persistence for run monitoring and user feedback."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from repo_research.models import (
    AnswerSnapshot,
    ErrorCountSummary,
    EvaluatableAnswerSnapshot,
    EvaluationDashboardSummary,
    EvaluationMetricAverage,
    EvaluationResultList,
    EvaluationResultSummary,
    EvaluationRunKindAverage,
    EvaluationRunList,
    EvaluationRunRecord,
    EvaluationRunStatus,
    EvaluationRunSummary,
    EvaluationSourceType,
    EvidenceItem,
    FeedbackEvent,
    FeedbackUsefulSummary,
    LatencyByRunKind,
    ModelUsageSummary,
    MonitoringFeedbackFilter,
    MonitoringRunDetail,
    MonitoringRunFeedback,
    MonitoringRunList,
    MonitoringRunSummary,
    MonitoringSummary,
    PersistedEvaluationResult,
    RagAnswer,
    RagMode,
    RagRunTrace,
    ResearchAnswer,
    RetrievalEvaluationList,
    RetrievalEvaluationSummary,
    RetrievalMode,
    RetrievalVolumeSummary,
    RunKind,
    RunKindCount,
)

ConnectionFactory = Callable[..., AbstractContextManager[Any]]


class NoOpRecordingStore:
    """Recording store used when telemetry persistence is not configured."""

    def initialize(self) -> None:
        """Match the live store lifecycle without creating external state."""

    def record_run(self, *, run_kind: RunKind, trace: RagRunTrace) -> None:
        """Accept run traces without persisting them."""
        del run_kind, trace

    def record_answer_snapshot(self, snapshot: AnswerSnapshot) -> None:
        """Accept answer snapshots without persisting them."""
        del snapshot

    def record_feedback(self, event: FeedbackEvent) -> None:
        """Accept feedback without persisting it."""
        del event

    def record_evaluation_run(self, evaluation_run: EvaluationRunRecord) -> None:
        """Accept evaluation-run metadata without persisting it."""
        del evaluation_run

    def record_evaluation_result(self, result: PersistedEvaluationResult) -> None:
        """Accept evaluation-result metadata without persisting it."""
        del result

    def list_answer_snapshots_for_evaluation(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        request_ids: list[str] | None = None,
    ) -> list[EvaluatableAnswerSnapshot]:
        """Return no answer snapshots when telemetry persistence is disabled."""
        del limit, run_kind, repository_name, request_ids
        return []

    def evaluation_summary(self) -> EvaluationDashboardSummary:
        """Return an empty evaluation dashboard summary."""
        return EvaluationDashboardSummary(
            total_runs=0,
            completed_runs=0,
            failed_runs=0,
            total_results=0,
            unsupported_claim_rate=0,
        )

    def list_evaluation_runs(
        self,
        *,
        limit: int = 50,
        source_type: EvaluationSourceType | None = None,
        status: EvaluationRunStatus | None = None,
    ) -> EvaluationRunList:
        """Return no evaluation runs when persistence is disabled."""
        del limit, source_type, status
        return EvaluationRunList()

    def list_evaluation_results(
        self,
        *,
        limit: int = 50,
        source_type: EvaluationSourceType | None = None,
        run_kind: RunKind | None = None,
        context_label: str | None = None,
    ) -> EvaluationResultList:
        """Return no evaluation results when persistence is disabled."""
        del limit, source_type, run_kind, context_label
        return EvaluationResultList()

    def list_retrieval_evaluation_results(self) -> RetrievalEvaluationList:
        """Return no retrieval-evaluation rows when persistence is disabled."""
        return RetrievalEvaluationList()

    def monitoring_summary(self) -> MonitoringSummary:
        """Return an empty dashboard summary."""
        return MonitoringSummary(total_runs=0)

    def list_monitoring_runs(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        has_error: bool | None = None,
        feedback: MonitoringFeedbackFilter = MonitoringFeedbackFilter.ALL,
    ) -> MonitoringRunList:
        """Return an empty run history."""
        del limit, run_kind, repository_name, has_error, feedback
        return MonitoringRunList()

    def get_monitoring_run(self, request_id: str) -> MonitoringRunDetail | None:
        """Return no detail when telemetry persistence is disabled."""
        del request_id
        return None


@dataclass(frozen=True)
class PostgresRecordingStore:
    """Persist run summaries and feedback using explicit PostgreSQL SQL."""

    dsn: str
    connection_factory: ConnectionFactory = psycopg.connect

    def initialize(self) -> None:
        """Create monitoring and feedback tables when they do not exist."""
        with self._connect() as connection:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)

    def record_run(self, *, run_kind: RunKind, trace: RagRunTrace) -> None:
        """Persist one run trace without answer text or source evidence content."""
        with self._connect() as connection:
            connection.execute(
                _UPSERT_MONITORING_RUN,
                {
                    "request_id": trace.request_id,
                    "session_id": trace.session_id,
                    "run_kind": run_kind.value,
                    "started_at": trace.started_at,
                    "completed_at": trace.completed_at,
                    "repository_id": trace.repository_id,
                    "repository_name": trace.repository_name,
                    "branch": trace.branch,
                    "commit_hash": trace.commit_hash,
                    "question_mode": trace.question_mode.value,
                    "retrieval_mode": trace.retrieval_mode.value,
                    "retrieval_limit": trace.retrieval_limit,
                    "retrieved_chunk_count": trace.retrieved_chunk_count,
                    "unique_file_count": trace.unique_file_count,
                    "evidence_count": len(trace.evidence_ids),
                    "latency_ms_total": trace.latency_ms_total,
                    "latency_ms_retrieval": trace.latency_ms_retrieval,
                    "latency_ms_model": trace.latency_ms_model,
                    "tool_call_count": trace.tool_call_count,
                    "insufficient_evidence": trace.insufficient_evidence,
                    "error_type": trace.error_type,
                    "error_message": trace.error_message,
                    "total_estimated_cost_usd": trace.total_estimated_cost_usd,
                    "model_usage": Jsonb(
                        [usage.model_dump(mode="json") for usage in trace.model_usage]
                    ),
                },
            )

    def record_feedback(self, event: FeedbackEvent) -> None:
        """Persist a user feedback event linked by session ID and optional request."""
        with self._connect() as connection:
            connection.execute(
                _INSERT_FEEDBACK_EVENT,
                {
                    "feedback_id": event.feedback_id,
                    "session_id": event.session_id,
                    "request_id": event.request_id,
                    "run_kind": event.run_kind.value if event.run_kind else None,
                    "useful": event.useful,
                    "comment": event.comment,
                    "submitted_at": event.submitted_at,
                },
            )

    def record_answer_snapshot(self, snapshot: AnswerSnapshot) -> None:
        """Persist the answer shape needed for later quality evaluation."""
        with self._connect() as connection:
            connection.execute(
                _UPSERT_ANSWER_SNAPSHOT,
                {
                    "request_id": snapshot.request_id,
                    "session_id": snapshot.session_id,
                    "run_kind": snapshot.run_kind.value,
                    "question": snapshot.question,
                    "answer": Jsonb(snapshot.answer.model_dump(mode="json")),
                    "evidence": Jsonb(
                        [item.model_dump(mode="json") for item in snapshot.evidence]
                    ),
                    "repository_id": snapshot.repository_id,
                    "repository_name": snapshot.repository_name,
                    "branch": snapshot.branch,
                    "commit_hash": snapshot.commit_hash,
                    "question_mode": snapshot.question_mode.value,
                    "retrieval_mode": snapshot.retrieval_mode.value,
                    "retrieval_limit": snapshot.retrieval_limit,
                    "created_at": snapshot.created_at,
                },
            )

    def record_evaluation_run(self, evaluation_run: EvaluationRunRecord) -> None:
        """Persist one evaluation batch lifecycle record."""
        with self._connect() as connection:
            connection.execute(
                _UPSERT_EVALUATION_RUN,
                {
                    "evaluation_run_id": evaluation_run.evaluation_run_id,
                    "source_type": evaluation_run.source_type.value,
                    "source_label": evaluation_run.source_label,
                    "judge_model": evaluation_run.judge_model,
                    "status": evaluation_run.status.value,
                    "started_at": evaluation_run.started_at,
                    "completed_at": evaluation_run.completed_at,
                    "error_message": evaluation_run.error_message,
                },
            )

    def record_evaluation_result(self, result: PersistedEvaluationResult) -> None:
        """Persist one judged answer-quality result."""
        with self._connect() as connection:
            connection.execute(
                _UPSERT_EVALUATION_RESULT,
                {
                    "result_id": result.result_id,
                    "evaluation_run_id": result.evaluation_run_id,
                    "record_id": result.record_id,
                    "request_id": result.request_id,
                    "run_kind": result.run_kind.value if result.run_kind else None,
                    "question": result.question,
                    "answer_correctness": result.answer_correctness,
                    "faithfulness": result.faithfulness,
                    "citation_precision": result.citation_precision,
                    "reference_coverage": result.reference_coverage,
                    "answer_relevance": result.answer_relevance,
                    "presentation_quality": result.presentation_quality,
                    "unsupported_claim_count": result.unsupported_claim_count,
                    "feedback_useful": result.feedback_useful,
                    "feedback_not_useful": result.feedback_not_useful,
                    "latency_ms_total": result.latency_ms_total,
                    "total_estimated_cost_usd": result.total_estimated_cost_usd,
                    "notes": result.notes,
                    "created_at": result.created_at,
                },
            )

    def list_answer_snapshots_for_evaluation(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        request_ids: list[str] | None = None,
    ) -> list[EvaluatableAnswerSnapshot]:
        """Return recent monitored answers with context needed by evaluation."""
        with self._connect() as connection:
            rows = list(
                connection.execute(
                    _SELECT_ANSWER_SNAPSHOTS_FOR_EVALUATION,
                    {
                        "limit": limit,
                        "run_kind": run_kind.value if run_kind else None,
                        "repository_name": repository_name,
                        "request_ids": request_ids or None,
                    },
                ).fetchall()
            )
        return [_evaluatable_answer_snapshot_from_row(row) for row in rows]

    def evaluation_summary(self) -> EvaluationDashboardSummary:
        """Return aggregate answer-evaluation dashboard data."""
        with self._connect() as connection:
            run_rows = list(connection.execute(_SELECT_EVALUATION_RUN_ROWS).fetchall())
            result_rows = list(
                connection.execute(_SELECT_EVALUATION_RESULT_ROWS).fetchall()
            )
        return _build_evaluation_summary(run_rows=run_rows, result_rows=result_rows)

    def list_evaluation_runs(
        self,
        *,
        limit: int = 50,
        source_type: EvaluationSourceType | None = None,
        status: EvaluationRunStatus | None = None,
    ) -> EvaluationRunList:
        """Return recent persisted answer-evaluation batches."""
        with self._connect() as connection:
            run_rows = list(connection.execute(_SELECT_EVALUATION_RUN_ROWS).fetchall())
            result_rows = list(
                connection.execute(_SELECT_EVALUATION_RESULT_ROWS).fetchall()
            )
        runs = [
            _evaluation_run_summary_from_row(row, result_rows)
            for row in sorted(
                run_rows,
                key=lambda item: item["started_at"],
                reverse=True,
            )
        ]
        filtered = [
            run
            for run in runs
            if (source_type is None or run.source_type is source_type)
            and (status is None or run.status is status)
        ]
        return EvaluationRunList(runs=filtered[:limit])

    def list_evaluation_results(
        self,
        *,
        limit: int = 50,
        source_type: EvaluationSourceType | None = None,
        run_kind: RunKind | None = None,
        context_label: str | None = None,
    ) -> EvaluationResultList:
        """Return recent persisted judged answer results."""
        with self._connect() as connection:
            rows = list(connection.execute(_SELECT_EVALUATION_RESULT_ROWS).fetchall())
        results = [
            _evaluation_result_summary_from_row(row)
            for row in sorted(
                rows,
                key=lambda item: item["created_at"],
                reverse=True,
            )
        ]
        filtered = [
            result
            for result in results
            if (source_type is None or result.source_type is source_type)
            and (run_kind is None or result.run_kind is run_kind)
            and (
                context_label is None
                or result.context_label.lower() == context_label.lower()
            )
        ]
        return EvaluationResultList(results=filtered[:limit])

    def list_retrieval_evaluation_results(self) -> RetrievalEvaluationList:
        """Return persisted retrieval-evaluation metrics for dashboard highlights."""
        with self._connect() as connection:
            rows = list(
                connection.execute(_SELECT_RETRIEVAL_EVALUATION_RESULT_ROWS).fetchall()
            )
        results = [
            _retrieval_evaluation_summary_from_row(row)
            for row in sorted(
                rows,
                key=lambda item: (
                    str(item["dataset"]).lower() != "held-out",
                    not bool(item["selected"]),
                    str(item["mode"]),
                ),
            )
        ]
        return RetrievalEvaluationList(results=results)

    def monitoring_summary(self) -> MonitoringSummary:
        """Return dashboard aggregates from persisted monitoring and feedback."""
        with self._connect() as connection:
            run_rows = list(connection.execute(_SELECT_MONITORING_ROWS).fetchall())
            feedback_rows = list(connection.execute(_SELECT_FEEDBACK_ROWS).fetchall())
        return _build_summary(run_rows=run_rows, feedback_rows=feedback_rows)

    def list_monitoring_runs(
        self,
        *,
        limit: int = 50,
        run_kind: RunKind | None = None,
        repository_name: str | None = None,
        has_error: bool | None = None,
        feedback: MonitoringFeedbackFilter = MonitoringFeedbackFilter.ALL,
    ) -> MonitoringRunList:
        """Return recent persisted monitoring runs for reviewer inspection."""
        with self._connect() as connection:
            run_rows = list(
                connection.execute(_SELECT_MONITORING_RUN_HISTORY).fetchall()
            )
            feedback_rows = list(
                connection.execute(_SELECT_FEEDBACK_DETAIL_ROWS).fetchall()
            )
        runs = [
            _run_summary_from_row(row, feedback_rows)
            for row in sorted(
                run_rows,
                key=lambda item: item["completed_at"],
                reverse=True,
            )
        ]
        filtered = [
            run
            for run in runs
            if _matches_run_filters(
                run,
                run_kind=run_kind,
                repository_name=repository_name,
                has_error=has_error,
                feedback=feedback,
            )
        ]
        return MonitoringRunList(runs=filtered[:limit])

    def get_monitoring_run(self, request_id: str) -> MonitoringRunDetail | None:
        """Return detailed persisted monitoring data for one request."""
        with self._connect() as connection:
            run_rows = list(
                connection.execute(
                    _SELECT_MONITORING_RUN_DETAIL,
                    {"request_id": request_id},
                ).fetchall()
            )
            feedback_rows = list(
                connection.execute(_SELECT_FEEDBACK_DETAIL_ROWS).fetchall()
            )
        for row in run_rows:
            if row["request_id"] == request_id:
                return _run_detail_from_row(row, feedback_rows)
        return None

    def _connect(self) -> AbstractContextManager[Any]:
        return self.connection_factory(
            self.dsn,
            autocommit=True,
            row_factory=dict_row,
        )


def _build_summary(
    *,
    run_rows: list[dict[str, Any]],
    feedback_rows: list[dict[str, Any]],
) -> MonitoringSummary:
    counts_by_kind: dict[RunKind, int] = {}
    latency_totals_by_kind: dict[RunKind, int] = {}
    retrieval_total = 0
    unique_file_total = 0
    errors_by_type: dict[str, int] = {}
    model_usage_by_key: dict[tuple[str, str], dict[str, int | Decimal | None]] = {}

    for row in run_rows:
        run_kind = RunKind(str(row["run_kind"]))
        counts_by_kind[run_kind] = counts_by_kind.get(run_kind, 0) + 1
        latency_total = int(row["latency_ms_total"])
        latency_totals_by_kind[run_kind] = (
            latency_totals_by_kind.get(run_kind, 0) + latency_total
        )
        retrieval_total += int(row["retrieved_chunk_count"])
        unique_file_total += int(row["unique_file_count"])
        error_type = row.get("error_type")
        if isinstance(error_type, str) and error_type:
            errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1
        _accumulate_model_usage(model_usage_by_key, row.get("model_usage") or [])

    useful_count = sum(1 for row in feedback_rows if row["useful"] is True)
    not_useful_count = sum(1 for row in feedback_rows if row["useful"] is False)

    return MonitoringSummary(
        total_runs=len(run_rows),
        runs_by_kind=[
            RunKindCount(run_kind=run_kind, count=count)
            for run_kind, count in sorted(
                counts_by_kind.items(), key=lambda item: item[0]
            )
        ],
        average_latency_by_kind=[
            LatencyByRunKind(
                run_kind=run_kind,
                average_latency_ms=latency_totals_by_kind[run_kind] / count,
            )
            for run_kind, count in sorted(
                counts_by_kind.items(), key=lambda item: item[0]
            )
        ],
        retrieval_volume=RetrievalVolumeSummary(
            retrieved_chunk_count=retrieval_total,
            unique_file_count=unique_file_total,
        ),
        model_usage_by_model=[
            ModelUsageSummary(
                provider=provider,
                model=model,
                input_tokens=int(values["input_tokens"] or 0),
                output_tokens=int(values["output_tokens"] or 0),
                total_tokens=int(values["total_tokens"] or 0),
                estimated_cost_usd=_decimal_or_none(values["estimated_cost_usd"]),
            )
            for (provider, model), values in sorted(model_usage_by_key.items())
        ],
        feedback=FeedbackUsefulSummary(
            useful=useful_count,
            not_useful=not_useful_count,
        ),
        errors_by_type=[
            ErrorCountSummary(error_type=error_type, count=count)
            for error_type, count in sorted(errors_by_type.items())
        ],
    )


def _build_evaluation_summary(
    *,
    run_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> EvaluationDashboardSummary:
    metric_names = [
        "answer_correctness",
        "faithfulness",
        "citation_precision",
        "reference_coverage",
        "answer_relevance",
        "presentation_quality",
    ]
    completed_runs = sum(
        1 for row in run_rows if row["status"] == EvaluationRunStatus.COMPLETED.value
    )
    failed_runs = sum(
        1 for row in run_rows if row["status"] == EvaluationRunStatus.FAILED.value
    )
    total_results = len(result_rows)
    results_with_unsupported_claims = sum(
        1 for row in result_rows if int(row["unsupported_claim_count"]) > 0
    )
    average_score = (
        sum(_average_result_score(row) for row in result_rows) / total_results
        if total_results
        else None
    )
    by_run_kind: dict[RunKind | None, list[dict[str, Any]]] = {}
    for row in result_rows:
        run_kind_value = row.get("run_kind")
        run_kind = RunKind(str(run_kind_value)) if run_kind_value else None
        by_run_kind.setdefault(run_kind, []).append(row)

    return EvaluationDashboardSummary(
        total_runs=len(run_rows),
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        total_results=total_results,
        average_score=average_score,
        unsupported_claim_rate=(
            results_with_unsupported_claims / total_results if total_results else 0
        ),
        average_by_run_kind=[
            EvaluationRunKindAverage(
                run_kind=run_kind,
                average_score=sum(_average_result_score(row) for row in rows)
                / len(rows),
                result_count=len(rows),
                unsupported_claim_count=sum(
                    int(row["unsupported_claim_count"]) for row in rows
                ),
            )
            for run_kind, rows in sorted(
                by_run_kind.items(),
                key=lambda item: item[0].value if item[0] else "",
            )
        ],
        metric_averages=[
            EvaluationMetricAverage(
                metric=metric,
                source_type=None,
                average_score=sum(float(row[metric]) for row in scored_rows)
                / len(scored_rows),
                result_count=len(scored_rows),
            )
            for metric in metric_names
            if (
                scored_rows := [
                    row for row in result_rows if row.get(metric) is not None
                ]
            )
        ],
    )


def _evaluation_run_summary_from_row(
    row: dict[str, Any], result_rows: list[dict[str, Any]]
) -> EvaluationRunSummary:
    run_results = [
        result
        for result in result_rows
        if result["evaluation_run_id"] == row["evaluation_run_id"]
    ]
    return EvaluationRunSummary(
        evaluation_run_id=str(row["evaluation_run_id"]),
        source_type=EvaluationSourceType(str(row["source_type"])),
        source_label=str(row["source_label"]),
        context_labels=_evaluation_context_labels(
            source_label=str(row["source_label"]),
            result_rows=run_results,
        ),
        judge_model=str(row["judge_model"]),
        status=EvaluationRunStatus(str(row["status"])),
        started_at=row["started_at"],
        completed_at=row.get("completed_at"),
        error_message=row.get("error_message"),
        result_count=len(run_results),
        average_score=(
            sum(_average_result_score(result) for result in run_results)
            / len(run_results)
            if run_results
            else None
        ),
        unsupported_claim_count=sum(
            int(result["unsupported_claim_count"]) for result in run_results
        ),
    )


def _evaluation_result_summary_from_row(row: dict[str, Any]) -> EvaluationResultSummary:
    run_kind_value = row.get("run_kind")
    return EvaluationResultSummary(
        result_id=str(row["result_id"]),
        evaluation_run_id=str(row["evaluation_run_id"]),
        source_type=EvaluationSourceType(str(row["source_type"])),
        source_label=str(row["source_label"]),
        context_label=_evaluation_context_label(row),
        repository_name=row.get("repository_name"),
        branch=row.get("branch"),
        commit_hash=row.get("commit_hash"),
        record_id=row.get("record_id"),
        request_id=row.get("request_id"),
        run_kind=RunKind(str(run_kind_value)) if run_kind_value else None,
        question=str(row["question"]),
        answer_correctness=_float_or_none(row.get("answer_correctness")),
        faithfulness=float(row["faithfulness"]),
        citation_precision=float(row["citation_precision"]),
        reference_coverage=_float_or_none(row.get("reference_coverage")),
        answer_relevance=float(row["answer_relevance"]),
        presentation_quality=float(row["presentation_quality"]),
        average_score=_average_result_score(row),
        unsupported_claim_count=int(row["unsupported_claim_count"]),
        feedback_useful=int(row["feedback_useful"]),
        feedback_not_useful=int(row["feedback_not_useful"]),
        latency_ms_total=row.get("latency_ms_total"),
        total_estimated_cost_usd=row.get("total_estimated_cost_usd"),
        notes=str(row.get("notes") or ""),
        answer_evidence=_evidence_items_from_json(row.get("answer_evidence")),
        created_at=row["created_at"],
    )


def _retrieval_evaluation_summary_from_row(
    row: dict[str, Any],
) -> RetrievalEvaluationSummary:
    return RetrievalEvaluationSummary(
        dataset=str(row["dataset"]),
        mode=RetrievalMode(str(row["mode"])),
        source_label=str(row["source_label"]),
        limit=int(row["limit_value"]),
        record_count=int(row["record_count"]),
        file_hit_rate=float(row["file_hit_rate"]),
        file_mrr=float(row["file_mrr"]),
        file_recall=float(row["file_recall"]),
        file_precision=float(row["file_precision"]),
        symbol_hit_rate=float(row["symbol_hit_rate"]),
        selected=bool(row["selected"]),
        measured_at=row["measured_at"],
    )


def _average_result_score(row: dict[str, Any]) -> float:
    scores = [
        float(row[metric])
        for metric in (
            "faithfulness",
            "citation_precision",
            "answer_relevance",
            "presentation_quality",
        )
        if row.get(metric) is not None
    ]
    return sum(scores) / len(scores) if scores else 0


def _evaluation_context_label(row: dict[str, Any]) -> str:
    repository_name = row.get("repository_name")
    if repository_name:
        return str(repository_name)
    return str(row["source_label"])


def _evaluation_context_labels(
    *, source_label: str, result_rows: list[dict[str, Any]]
) -> list[str]:
    labels = sorted({_evaluation_context_label(row) for row in result_rows})
    return labels or [source_label]


def _evidence_items_from_json(value: Any) -> list[EvidenceItem]:
    if not value:
        return []
    return [EvidenceItem.model_validate(item) for item in value]


def _accumulate_model_usage(
    totals: dict[tuple[str, str], dict[str, int | Decimal | None]],
    usage_rows: list[dict[str, Any]],
) -> None:
    for usage in usage_rows:
        provider = str(usage.get("provider") or "unknown")
        model = str(usage.get("model") or "unknown")
        key = (provider, model)
        values = totals.setdefault(
            key,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": Decimal("0"),
            },
        )
        values["input_tokens"] = int(values["input_tokens"] or 0) + int(
            usage.get("input_tokens") or 0
        )
        values["output_tokens"] = int(values["output_tokens"] or 0) + int(
            usage.get("output_tokens") or 0
        )
        values["total_tokens"] = int(values["total_tokens"] or 0) + int(
            usage.get("total_tokens") or 0
        )
        raw_cost = usage.get("estimated_cost_usd")
        if raw_cost is None or values["estimated_cost_usd"] is None:
            values["estimated_cost_usd"] = None
        else:
            values["estimated_cost_usd"] = Decimal(
                str(values["estimated_cost_usd"])
            ) + Decimal(str(raw_cost))


def _decimal_or_none(value: int | Decimal | None) -> Decimal | None:
    return value if isinstance(value, Decimal) else None


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)


def _run_summary_from_row(
    row: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
) -> MonitoringRunSummary:
    useful, not_useful = _feedback_counts(row, feedback_rows)
    return MonitoringRunSummary(
        request_id=str(row["request_id"]),
        session_id=str(row["session_id"]),
        run_kind=RunKind(str(row["run_kind"])),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        repository_name=str(row["repository_name"]),
        branch=str(row["branch"]),
        commit_hash=str(row["commit_hash"]),
        question_mode=RagMode(str(row["question_mode"])),
        retrieval_mode=RetrievalMode(str(row["retrieval_mode"])),
        retrieved_chunk_count=int(row["retrieved_chunk_count"]),
        unique_file_count=int(row["unique_file_count"]),
        evidence_count=int(row["evidence_count"]),
        latency_ms_total=int(row["latency_ms_total"]),
        latency_ms_retrieval=int(row["latency_ms_retrieval"]),
        latency_ms_model=_optional_int(row.get("latency_ms_model")),
        tool_call_count=int(row["tool_call_count"]),
        insufficient_evidence=bool(row["insufficient_evidence"]),
        has_error=bool(row.get("error_type")),
        feedback_useful=useful,
        feedback_not_useful=not_useful,
        total_estimated_cost_usd=_optional_decimal(row.get("total_estimated_cost_usd")),
    )


def _run_detail_from_row(
    row: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
) -> MonitoringRunDetail:
    summary = _run_summary_from_row(row, feedback_rows)
    return MonitoringRunDetail(
        **summary.model_dump(),
        repository_id=str(row["repository_id"]),
        retrieval_limit=int(row["retrieval_limit"]),
        error_type=row.get("error_type"),
        error_message=row.get("error_message"),
        model_usage=row.get("model_usage") or [],
        feedback_events=[
            MonitoringRunFeedback(
                feedback_id=str(feedback["feedback_id"]),
                useful=bool(feedback["useful"]),
                comment=feedback.get("comment"),
                submitted_at=feedback["submitted_at"],
            )
            for feedback in feedback_rows
            if _feedback_matches_run(feedback, row)
        ],
    )


def _evaluatable_answer_snapshot_from_row(
    row: dict[str, Any],
) -> EvaluatableAnswerSnapshot:
    run_kind = RunKind(str(row["run_kind"]))
    answer_data = row["answer"]
    return EvaluatableAnswerSnapshot(
        request_id=str(row["request_id"]),
        session_id=str(row["session_id"]),
        run_kind=run_kind,
        question=str(row["question"]),
        answer=_answer_from_row(run_kind=run_kind, answer_data=answer_data),
        evidence=row.get("evidence") or [],
        repository_id=str(row["repository_id"]),
        repository_name=str(row["repository_name"]),
        branch=str(row["branch"]),
        commit_hash=str(row["commit_hash"]),
        question_mode=RagMode(str(row["question_mode"])),
        retrieval_mode=RetrievalMode(str(row["retrieval_mode"])),
        retrieval_limit=int(row["retrieval_limit"]),
        created_at=row["created_at"],
        feedback_useful=int(row["feedback_useful"]),
        feedback_not_useful=int(row["feedback_not_useful"]),
        latency_ms_total=_optional_int(row.get("latency_ms_total")),
        total_estimated_cost_usd=_optional_decimal(row.get("total_estimated_cost_usd")),
    )


def _answer_from_row(
    *, run_kind: RunKind, answer_data: Any
) -> RagAnswer | ResearchAnswer:
    if run_kind is RunKind.AGENTIC:
        return ResearchAnswer.model_validate(answer_data)
    return RagAnswer.model_validate(answer_data)


def _matches_run_filters(
    run: MonitoringRunSummary,
    *,
    run_kind: RunKind | None,
    repository_name: str | None,
    has_error: bool | None,
    feedback: MonitoringFeedbackFilter,
) -> bool:
    if run_kind is not None and run.run_kind != run_kind:
        return False
    if repository_name and repository_name.lower() not in run.repository_name.lower():
        return False
    if has_error is not None and run.has_error != has_error:
        return False
    if feedback == MonitoringFeedbackFilter.USEFUL and run.feedback_useful == 0:
        return False
    if feedback == MonitoringFeedbackFilter.NOT_USEFUL and run.feedback_not_useful == 0:
        return False
    if (
        feedback == MonitoringFeedbackFilter.NONE
        and run.feedback_useful + run.feedback_not_useful > 0
    ):
        return False
    return True


def _feedback_counts(
    run_row: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    useful = 0
    not_useful = 0
    for feedback in feedback_rows:
        if not _feedback_matches_run(feedback, run_row):
            continue
        if feedback["useful"] is True:
            useful += 1
        else:
            not_useful += 1
    return useful, not_useful


def _feedback_matches_run(
    feedback: dict[str, Any],
    run_row: dict[str, Any],
) -> bool:
    if feedback.get("request_id") == run_row["request_id"]:
        return True
    return (
        feedback.get("request_id") is None
        and feedback.get("session_id") == run_row["session_id"]
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS monitoring_runs (
        request_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL CHECK (length(session_id) > 0),
        run_kind TEXT NOT NULL CHECK (run_kind IN ('direct', 'agentic')),
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ NOT NULL,
        repository_id TEXT NOT NULL,
        repository_name TEXT NOT NULL,
        branch TEXT NOT NULL,
        commit_hash TEXT NOT NULL,
        question_mode TEXT NOT NULL,
        retrieval_mode TEXT NOT NULL,
        retrieval_limit INTEGER NOT NULL,
        retrieved_chunk_count INTEGER NOT NULL,
        unique_file_count INTEGER NOT NULL,
        evidence_count INTEGER NOT NULL,
        latency_ms_total INTEGER NOT NULL,
        latency_ms_retrieval INTEGER NOT NULL,
        latency_ms_model INTEGER,
        tool_call_count INTEGER NOT NULL,
        insufficient_evidence BOOLEAN NOT NULL,
        error_type TEXT,
        error_message TEXT,
        total_estimated_cost_usd NUMERIC,
        model_usage JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS monitoring_runs_session_id_idx
    ON monitoring_runs (session_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS monitoring_runs_completed_at_idx
    ON monitoring_runs (completed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_events (
        feedback_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL CHECK (length(session_id) > 0),
        request_id TEXT REFERENCES monitoring_runs (request_id) ON DELETE SET NULL,
        run_kind TEXT CHECK (run_kind IN ('direct', 'agentic')),
        useful BOOLEAN NOT NULL,
        comment TEXT,
        submitted_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS feedback_events_session_id_idx
    ON feedback_events (session_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS answer_snapshots (
        request_id TEXT PRIMARY KEY REFERENCES monitoring_runs (request_id)
            ON DELETE CASCADE,
        session_id TEXT NOT NULL CHECK (length(session_id) > 0),
        run_kind TEXT NOT NULL CHECK (run_kind IN ('direct', 'agentic')),
        question TEXT NOT NULL CHECK (length(question) > 0),
        answer JSONB NOT NULL,
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        repository_id TEXT NOT NULL,
        repository_name TEXT NOT NULL,
        branch TEXT NOT NULL,
        commit_hash TEXT NOT NULL,
        question_mode TEXT NOT NULL,
        retrieval_mode TEXT NOT NULL,
        retrieval_limit INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS answer_snapshots_session_id_idx
    ON answer_snapshots (session_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS answer_snapshots_created_at_idx
    ON answer_snapshots (created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_runs (
        evaluation_run_id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL CHECK (
            source_type IN ('dataset', 'monitored_runs')
        ),
        source_label TEXT NOT NULL CHECK (length(source_label) > 0),
        judge_model TEXT NOT NULL CHECK (length(judge_model) > 0),
        status TEXT NOT NULL CHECK (
            status IN ('pending', 'running', 'completed', 'failed')
        ),
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS evaluation_runs_started_at_idx
    ON evaluation_runs (started_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluation_results (
        result_id TEXT PRIMARY KEY,
        evaluation_run_id TEXT NOT NULL REFERENCES evaluation_runs
            (evaluation_run_id) ON DELETE CASCADE,
        record_id TEXT,
        request_id TEXT REFERENCES answer_snapshots (request_id) ON DELETE SET NULL,
        run_kind TEXT CHECK (run_kind IN ('direct', 'agentic')),
        question TEXT NOT NULL CHECK (length(question) > 0),
        answer_correctness NUMERIC,
        faithfulness NUMERIC NOT NULL,
        citation_precision NUMERIC NOT NULL,
        reference_coverage NUMERIC,
        answer_relevance NUMERIC NOT NULL,
        presentation_quality NUMERIC NOT NULL,
        unsupported_claim_count INTEGER NOT NULL,
        feedback_useful INTEGER NOT NULL DEFAULT 0,
        feedback_not_useful INTEGER NOT NULL DEFAULT 0,
        latency_ms_total INTEGER,
        total_estimated_cost_usd NUMERIC,
        notes TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS answer_correctness NUMERIC
    """,
    """
    ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS faithfulness NUMERIC NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS citation_precision NUMERIC NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS reference_coverage NUMERIC
    """,
    """
    ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS answer_relevance NUMERIC NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS presentation_quality NUMERIC NOT NULL DEFAULT 0
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'evaluation_results'
              AND column_name = 'correctness'
        ) THEN
            UPDATE evaluation_results
            SET answer_correctness = COALESCE(answer_correctness, correctness),
                faithfulness = groundedness,
                citation_precision = citation_accuracy,
                reference_coverage = COALESCE(reference_coverage, completeness),
                answer_relevance = usefulness,
                presentation_quality = usefulness;
        END IF;
    END $$;
    """,
    """
    ALTER TABLE evaluation_results
    ALTER COLUMN faithfulness DROP DEFAULT,
    ALTER COLUMN citation_precision DROP DEFAULT,
    ALTER COLUMN answer_relevance DROP DEFAULT,
    ALTER COLUMN presentation_quality DROP DEFAULT
    """,
    """
    ALTER TABLE evaluation_results
    DROP COLUMN IF EXISTS correctness,
    DROP COLUMN IF EXISTS groundedness,
    DROP COLUMN IF EXISTS citation_accuracy,
    DROP COLUMN IF EXISTS completeness,
    DROP COLUMN IF EXISTS usefulness
    """,
    """
    CREATE INDEX IF NOT EXISTS evaluation_results_evaluation_run_id_idx
    ON evaluation_results (evaluation_run_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS evaluation_results_request_id_idx
    ON evaluation_results (request_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS retrieval_evaluation_results (
        dataset TEXT NOT NULL CHECK (length(dataset) > 0),
        mode TEXT NOT NULL CHECK (mode IN ('dense', 'sparse', 'hybrid')),
        source_label TEXT NOT NULL CHECK (length(source_label) > 0),
        limit_value INTEGER NOT NULL CHECK (limit_value > 0),
        record_count INTEGER NOT NULL CHECK (record_count >= 0),
        file_hit_rate NUMERIC NOT NULL CHECK (
            file_hit_rate >= 0 AND file_hit_rate <= 1
        ),
        file_mrr NUMERIC NOT NULL CHECK (file_mrr >= 0 AND file_mrr <= 1),
        file_recall NUMERIC NOT NULL CHECK (
            file_recall >= 0 AND file_recall <= 1
        ),
        file_precision NUMERIC NOT NULL CHECK (
            file_precision >= 0 AND file_precision <= 1
        ),
        symbol_hit_rate NUMERIC NOT NULL CHECK (
            symbol_hit_rate >= 0 AND symbol_hit_rate <= 1
        ),
        selected BOOLEAN NOT NULL DEFAULT false,
        measured_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (dataset, mode)
    )
    """,
    """
    INSERT INTO retrieval_evaluation_results (
        dataset,
        mode,
        source_label,
        limit_value,
        record_count,
        file_hit_rate,
        file_mrr,
        file_recall,
        file_precision,
        symbol_hit_rate,
        selected,
        measured_at
    ) VALUES
        (
            'Development', 'dense', 'eval/development.json local alpha smoke',
            5, 15, 0.400, 0.236, 0.272, 0.090, 0.357, false,
            '2026-08-13T00:00:00Z'
        ),
        (
            'Development', 'sparse', 'eval/development.json local alpha smoke',
            5, 15, 0.067, 0.033, 0.067, 0.013, 0.071, false,
            '2026-08-13T00:00:00Z'
        ),
        (
            'Development', 'hybrid', 'eval/development.json local alpha smoke',
            5, 15, 0.333, 0.163, 0.250, 0.077, 0.357, false,
            '2026-08-13T00:00:00Z'
        ),
        (
            'Held-out', 'dense', 'eval/held_out.json local alpha smoke',
            5, 15, 0.467, 0.313, 0.311, 0.200, 0.400, true,
            '2026-08-13T00:00:00Z'
        ),
        (
            'Held-out', 'sparse', 'eval/held_out.json local alpha smoke',
            5, 15, 0.133, 0.080, 0.100, 0.030, 0.267, false,
            '2026-08-13T00:00:00Z'
        ),
        (
            'Held-out', 'hybrid', 'eval/held_out.json local alpha smoke',
            5, 15, 0.400, 0.261, 0.278, 0.103, 0.333, false,
            '2026-08-13T00:00:00Z'
        )
    ON CONFLICT (dataset, mode) DO UPDATE SET
        source_label = EXCLUDED.source_label,
        limit_value = EXCLUDED.limit_value,
        record_count = EXCLUDED.record_count,
        file_hit_rate = EXCLUDED.file_hit_rate,
        file_mrr = EXCLUDED.file_mrr,
        file_recall = EXCLUDED.file_recall,
        file_precision = EXCLUDED.file_precision,
        symbol_hit_rate = EXCLUDED.symbol_hit_rate,
        selected = EXCLUDED.selected,
        measured_at = EXCLUDED.measured_at
    """,
)

_UPSERT_MONITORING_RUN = """
INSERT INTO monitoring_runs (
    request_id,
    session_id,
    run_kind,
    started_at,
    completed_at,
    repository_id,
    repository_name,
    branch,
    commit_hash,
    question_mode,
    retrieval_mode,
    retrieval_limit,
    retrieved_chunk_count,
    unique_file_count,
    evidence_count,
    latency_ms_total,
    latency_ms_retrieval,
    latency_ms_model,
    tool_call_count,
    insufficient_evidence,
    error_type,
    error_message,
    total_estimated_cost_usd,
    model_usage
) VALUES (
    %(request_id)s,
    %(session_id)s,
    %(run_kind)s,
    %(started_at)s,
    %(completed_at)s,
    %(repository_id)s,
    %(repository_name)s,
    %(branch)s,
    %(commit_hash)s,
    %(question_mode)s,
    %(retrieval_mode)s,
    %(retrieval_limit)s,
    %(retrieved_chunk_count)s,
    %(unique_file_count)s,
    %(evidence_count)s,
    %(latency_ms_total)s,
    %(latency_ms_retrieval)s,
    %(latency_ms_model)s,
    %(tool_call_count)s,
    %(insufficient_evidence)s,
    %(error_type)s,
    %(error_message)s,
    %(total_estimated_cost_usd)s,
    %(model_usage)s
)
ON CONFLICT (request_id) DO UPDATE SET
    session_id = EXCLUDED.session_id,
    run_kind = EXCLUDED.run_kind,
    completed_at = EXCLUDED.completed_at,
    retrieved_chunk_count = EXCLUDED.retrieved_chunk_count,
    unique_file_count = EXCLUDED.unique_file_count,
    evidence_count = EXCLUDED.evidence_count,
    latency_ms_total = EXCLUDED.latency_ms_total,
    latency_ms_retrieval = EXCLUDED.latency_ms_retrieval,
    latency_ms_model = EXCLUDED.latency_ms_model,
    tool_call_count = EXCLUDED.tool_call_count,
    insufficient_evidence = EXCLUDED.insufficient_evidence,
    error_type = EXCLUDED.error_type,
    error_message = EXCLUDED.error_message,
    total_estimated_cost_usd = EXCLUDED.total_estimated_cost_usd,
    model_usage = EXCLUDED.model_usage
"""

_INSERT_FEEDBACK_EVENT = """
INSERT INTO feedback_events (
    feedback_id,
    session_id,
    request_id,
    run_kind,
    useful,
    comment,
    submitted_at
) VALUES (
    %(feedback_id)s,
    %(session_id)s,
    %(request_id)s,
    %(run_kind)s,
    %(useful)s,
    %(comment)s,
    %(submitted_at)s
)
"""

_UPSERT_ANSWER_SNAPSHOT = """
INSERT INTO answer_snapshots (
    request_id,
    session_id,
    run_kind,
    question,
    answer,
    evidence,
    repository_id,
    repository_name,
    branch,
    commit_hash,
    question_mode,
    retrieval_mode,
    retrieval_limit,
    created_at
) VALUES (
    %(request_id)s,
    %(session_id)s,
    %(run_kind)s,
    %(question)s,
    %(answer)s,
    %(evidence)s,
    %(repository_id)s,
    %(repository_name)s,
    %(branch)s,
    %(commit_hash)s,
    %(question_mode)s,
    %(retrieval_mode)s,
    %(retrieval_limit)s,
    %(created_at)s
)
ON CONFLICT (request_id) DO UPDATE SET
    session_id = EXCLUDED.session_id,
    run_kind = EXCLUDED.run_kind,
    question = EXCLUDED.question,
    answer = EXCLUDED.answer,
    evidence = EXCLUDED.evidence,
    repository_id = EXCLUDED.repository_id,
    repository_name = EXCLUDED.repository_name,
    branch = EXCLUDED.branch,
    commit_hash = EXCLUDED.commit_hash,
    question_mode = EXCLUDED.question_mode,
    retrieval_mode = EXCLUDED.retrieval_mode,
    retrieval_limit = EXCLUDED.retrieval_limit,
    created_at = EXCLUDED.created_at
"""

_UPSERT_EVALUATION_RUN = """
INSERT INTO evaluation_runs (
    evaluation_run_id,
    source_type,
    source_label,
    judge_model,
    status,
    started_at,
    completed_at,
    error_message
) VALUES (
    %(evaluation_run_id)s,
    %(source_type)s,
    %(source_label)s,
    %(judge_model)s,
    %(status)s,
    %(started_at)s,
    %(completed_at)s,
    %(error_message)s
)
ON CONFLICT (evaluation_run_id) DO UPDATE SET
    source_type = EXCLUDED.source_type,
    source_label = EXCLUDED.source_label,
    judge_model = EXCLUDED.judge_model,
    status = EXCLUDED.status,
    completed_at = EXCLUDED.completed_at,
    error_message = EXCLUDED.error_message
"""

_UPSERT_EVALUATION_RESULT = """
INSERT INTO evaluation_results (
    result_id,
    evaluation_run_id,
    record_id,
    request_id,
    run_kind,
    question,
    answer_correctness,
    faithfulness,
    citation_precision,
    reference_coverage,
    answer_relevance,
    presentation_quality,
    unsupported_claim_count,
    feedback_useful,
    feedback_not_useful,
    latency_ms_total,
    total_estimated_cost_usd,
    notes,
    created_at
) VALUES (
    %(result_id)s,
    %(evaluation_run_id)s,
    %(record_id)s,
    %(request_id)s,
    %(run_kind)s,
    %(question)s,
    %(answer_correctness)s,
    %(faithfulness)s,
    %(citation_precision)s,
    %(reference_coverage)s,
    %(answer_relevance)s,
    %(presentation_quality)s,
    %(unsupported_claim_count)s,
    %(feedback_useful)s,
    %(feedback_not_useful)s,
    %(latency_ms_total)s,
    %(total_estimated_cost_usd)s,
    %(notes)s,
    %(created_at)s
)
ON CONFLICT (result_id) DO UPDATE SET
    evaluation_run_id = EXCLUDED.evaluation_run_id,
    record_id = EXCLUDED.record_id,
    request_id = EXCLUDED.request_id,
    run_kind = EXCLUDED.run_kind,
    question = EXCLUDED.question,
    answer_correctness = EXCLUDED.answer_correctness,
    faithfulness = EXCLUDED.faithfulness,
    citation_precision = EXCLUDED.citation_precision,
    reference_coverage = EXCLUDED.reference_coverage,
    answer_relevance = EXCLUDED.answer_relevance,
    presentation_quality = EXCLUDED.presentation_quality,
    unsupported_claim_count = EXCLUDED.unsupported_claim_count,
    feedback_useful = EXCLUDED.feedback_useful,
    feedback_not_useful = EXCLUDED.feedback_not_useful,
    latency_ms_total = EXCLUDED.latency_ms_total,
    total_estimated_cost_usd = EXCLUDED.total_estimated_cost_usd,
    notes = EXCLUDED.notes,
    created_at = EXCLUDED.created_at
"""

_SELECT_MONITORING_ROWS = """
SELECT
    run_kind,
    retrieved_chunk_count,
    unique_file_count,
    latency_ms_total,
    error_type,
    model_usage
FROM monitoring_runs
"""

_SELECT_FEEDBACK_ROWS = """
SELECT useful
FROM feedback_events
"""

_SELECT_ANSWER_SNAPSHOTS_FOR_EVALUATION = """
SELECT
    s.request_id,
    s.session_id,
    s.run_kind,
    s.question,
    s.answer,
    s.evidence,
    s.repository_id,
    s.repository_name,
    s.branch,
    s.commit_hash,
    s.question_mode,
    s.retrieval_mode,
    s.retrieval_limit,
    s.created_at,
    m.latency_ms_total,
    m.total_estimated_cost_usd,
    COALESCE(
        SUM(CASE WHEN f.useful IS TRUE THEN 1 ELSE 0 END),
        0
    )::integer AS feedback_useful,
    COALESCE(
        SUM(CASE WHEN f.useful IS FALSE THEN 1 ELSE 0 END),
        0
    )::integer AS feedback_not_useful
FROM answer_snapshots s
JOIN monitoring_runs m ON m.request_id = s.request_id
LEFT JOIN feedback_events f
    ON f.request_id = s.request_id
    OR (f.request_id IS NULL AND f.session_id = s.session_id)
WHERE (%(run_kind)s::text IS NULL OR s.run_kind = %(run_kind)s::text)
  AND (
      %(repository_name)s::text IS NULL
      OR lower(s.repository_name) LIKE (
          '%%' || lower(%(repository_name)s::text) || '%%'
      )
  )
  AND (
      %(request_ids)s::text[] IS NULL
      OR s.request_id = ANY(%(request_ids)s::text[])
  )
GROUP BY
    s.request_id,
    s.session_id,
    s.run_kind,
    s.question,
    s.answer,
    s.evidence,
    s.repository_id,
    s.repository_name,
    s.branch,
    s.commit_hash,
    s.question_mode,
    s.retrieval_mode,
    s.retrieval_limit,
    s.created_at,
    m.latency_ms_total,
    m.total_estimated_cost_usd
ORDER BY s.created_at DESC
LIMIT %(limit)s
"""

_SELECT_EVALUATION_RUN_ROWS = """
SELECT
    evaluation_run_id,
    source_type,
    source_label,
    judge_model,
    status,
    started_at,
    completed_at,
    error_message
FROM evaluation_runs
"""

_SELECT_EVALUATION_RESULT_ROWS = """
SELECT
    r.result_id,
    r.evaluation_run_id,
    e.source_type,
    e.source_label,
    s.repository_name,
    s.branch,
    s.commit_hash,
    r.record_id,
    r.request_id,
    r.run_kind,
    r.question,
    r.answer_correctness,
    r.faithfulness,
    r.citation_precision,
    r.reference_coverage,
    r.answer_relevance,
    r.presentation_quality,
    r.unsupported_claim_count,
    r.feedback_useful,
    r.feedback_not_useful,
    r.latency_ms_total,
    r.total_estimated_cost_usd,
    r.notes,
    s.evidence AS answer_evidence,
    r.created_at
FROM evaluation_results r
JOIN evaluation_runs e ON e.evaluation_run_id = r.evaluation_run_id
LEFT JOIN answer_snapshots s ON s.request_id = r.request_id
"""

_SELECT_RETRIEVAL_EVALUATION_RESULT_ROWS = """
SELECT
    dataset,
    mode,
    source_label,
    limit_value,
    record_count,
    file_hit_rate,
    file_mrr,
    file_recall,
    file_precision,
    symbol_hit_rate,
    selected,
    measured_at
FROM retrieval_evaluation_results
"""

_SELECT_MONITORING_RUN_HISTORY = """
SELECT
    request_id,
    session_id,
    run_kind,
    started_at,
    completed_at,
    repository_name,
    branch,
    commit_hash,
    question_mode,
    retrieval_mode,
    retrieved_chunk_count,
    unique_file_count,
    evidence_count,
    latency_ms_total,
    latency_ms_retrieval,
    latency_ms_model,
    tool_call_count,
    insufficient_evidence,
    error_type,
    total_estimated_cost_usd
FROM monitoring_runs
"""

_SELECT_MONITORING_RUN_DETAIL = """
SELECT
    request_id,
    session_id,
    run_kind,
    started_at,
    completed_at,
    repository_id,
    repository_name,
    branch,
    commit_hash,
    question_mode,
    retrieval_mode,
    retrieval_limit,
    retrieved_chunk_count,
    unique_file_count,
    evidence_count,
    latency_ms_total,
    latency_ms_retrieval,
    latency_ms_model,
    tool_call_count,
    insufficient_evidence,
    error_type,
    error_message,
    total_estimated_cost_usd,
    model_usage
FROM monitoring_runs
WHERE request_id = %(request_id)s
"""

_SELECT_FEEDBACK_DETAIL_ROWS = """
SELECT
    feedback_id,
    session_id,
    request_id,
    useful,
    comment,
    submitted_at
FROM feedback_events
"""
