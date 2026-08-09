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
    ErrorCountSummary,
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
    RagMode,
    RagRunTrace,
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

    def record_feedback(self, event: FeedbackEvent) -> None:
        """Accept feedback without persisting it."""
        del event

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
