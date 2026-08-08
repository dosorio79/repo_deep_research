"""Tests for PostgreSQL-backed monitoring and feedback recording."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from repo_research.models import (
    FeedbackEvent,
    ModelUsage,
    RagMode,
    RagRunTrace,
    RetrievalMode,
    RunKind,
)
from repo_research.recording_store import PostgresRecordingStore


class FakeCursor:
    """Tiny fetchable cursor returned by fake recording-store connections."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class FakeConnection:
    """Capture SQL statements without requiring a live PostgreSQL server."""

    def __init__(
        self,
        *,
        run_rows: list[dict[str, Any]] | None = None,
        feedback_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.run_rows = run_rows or []
        self.feedback_rows = feedback_rows or []
        self.executed: list[tuple[str, dict[str, Any] | None]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(
        self, statement: str, params: dict[str, Any] | None = None
    ) -> FakeCursor:
        self.executed.append((statement, params))
        if "FROM monitoring_runs" in statement:
            return FakeCursor(self.run_rows)
        if "FROM feedback_events" in statement:
            return FakeCursor(self.feedback_rows)
        return FakeCursor([])


class FakeConnectionFactory:
    """Return the same fake connection and capture connection options."""

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.calls: list[dict[str, Any]] = []

    def __call__(self, dsn: str, **kwargs: Any) -> FakeConnection:
        self.calls.append({"dsn": dsn, **kwargs})
        return self.connection


def test_recording_store_initializes_postgres_schema() -> None:
    connection = FakeConnection()
    factory = FakeConnectionFactory(connection)
    store = PostgresRecordingStore("postgresql://example", factory)

    store.initialize()

    statements = [statement for statement, _params in connection.executed]
    assert any(
        "CREATE TABLE IF NOT EXISTS monitoring_runs" in sql for sql in statements
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS feedback_events" in sql for sql in statements
    )
    assert any("monitoring_runs_session_id_idx" in sql for sql in statements)
    assert any("feedback_events_session_id_idx" in sql for sql in statements)
    assert factory.calls[0]["dsn"] == "postgresql://example"


def test_recording_store_persists_run_trace_summary() -> None:
    connection = FakeConnection()
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )
    trace = _trace()

    store.record_run(run_kind=RunKind.DIRECT, trace=trace)

    _statement, params = connection.executed[0]
    assert params is not None
    assert params["request_id"] == "request-1"
    assert params["session_id"] == "session-1"
    assert params["run_kind"] == "direct"
    assert params["retrieved_chunk_count"] == 3
    assert params["unique_file_count"] == 2
    assert params["evidence_count"] == 2
    assert params["total_estimated_cost_usd"] == Decimal("0.012")
    assert isinstance(params["model_usage"], Jsonb)
    assert params["model_usage"].obj == [
        {
            "provider": "openai",
            "model": "gpt-5-mini",
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cached_input_tokens": None,
            "reasoning_tokens": None,
            "estimated_cost_usd": "0.012",
            "pricing_source": "test",
            "pricing_version": "2026-08-07",
        }
    ]


def test_recording_store_persists_feedback_event() -> None:
    connection = FakeConnection()
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )
    event = FeedbackEvent(
        feedback_id="feedback-1",
        session_id="session-1",
        request_id="request-1",
        run_kind=RunKind.AGENTIC,
        useful=False,
        comment="Needs clearer targets.",
        submitted_at=datetime(2026, 8, 7, 12, tzinfo=UTC),
    )

    store.record_feedback(event)

    _statement, params = connection.executed[0]
    assert params is not None
    assert params["feedback_id"] == "feedback-1"
    assert params["session_id"] == "session-1"
    assert params["request_id"] == "request-1"
    assert params["run_kind"] == "agentic"
    assert params["useful"] is False
    assert params["comment"] == "Needs clearer targets."


def test_recording_store_returns_monitoring_summary() -> None:
    connection = FakeConnection(
        run_rows=[
            {
                "run_kind": "direct",
                "retrieved_chunk_count": 3,
                "unique_file_count": 2,
                "latency_ms_total": 100,
                "error_type": None,
                "model_usage": [
                    {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                        "estimated_cost_usd": "0.012",
                    }
                ],
            },
            {
                "run_kind": "agentic",
                "retrieved_chunk_count": 4,
                "unique_file_count": 3,
                "latency_ms_total": 300,
                "error_type": "ResearchBudgetExceeded",
                "model_usage": [
                    {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "input_tokens": 20,
                        "output_tokens": 10,
                        "total_tokens": 30,
                        "estimated_cost_usd": "0.024",
                    }
                ],
            },
        ],
        feedback_rows=[{"useful": True}, {"useful": False}, {"useful": False}],
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    summary = store.monitoring_summary()

    assert summary.total_runs == 2
    assert [(item.run_kind, item.count) for item in summary.runs_by_kind] == [
        (RunKind.AGENTIC, 1),
        (RunKind.DIRECT, 1),
    ]
    assert summary.retrieval_volume.retrieved_chunk_count == 7
    assert summary.retrieval_volume.unique_file_count == 5
    assert summary.model_usage_by_model[0].input_tokens == 30
    assert summary.model_usage_by_model[0].estimated_cost_usd == Decimal("0.036")
    assert summary.feedback.useful == 1
    assert summary.feedback.not_useful == 2
    assert summary.errors_by_type[0].error_type == "ResearchBudgetExceeded"


def _trace() -> RagRunTrace:
    return RagRunTrace(
        request_id="request-1",
        session_id="session-1",
        started_at=datetime(2026, 8, 7, 12, tzinfo=UTC),
        completed_at=datetime(2026, 8, 7, 12, 0, 1, tzinfo=UTC),
        repository_id="repo-id",
        repository_name="repo",
        branch="main",
        commit_hash="abc123",
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.HYBRID,
        retrieval_limit=5,
        retrieved_chunk_count=3,
        unique_file_count=2,
        evidence_ids=["E1", "E2"],
        latency_ms_total=1000,
        latency_ms_retrieval=200,
        latency_ms_model=800,
        model_usage=[
            ModelUsage(
                provider="openai",
                model="gpt-5-mini",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                estimated_cost_usd=Decimal("0.012"),
                pricing_source="test",
                pricing_version="2026-08-07",
            )
        ],
        total_estimated_cost_usd=Decimal("0.012"),
    )
