"""Tests for PostgreSQL-backed monitoring and feedback recording."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from repo_research.models import (
    AnswerSnapshot,
    EvaluationRunRecord,
    EvaluationRunStatus,
    EvaluationSourceType,
    EvidenceItem,
    FeedbackEvent,
    ModelUsage,
    MonitoringFeedbackFilter,
    PersistedEvaluationResult,
    RagAnswer,
    RagMode,
    RagRunTrace,
    ResearchAnswer,
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
        answer_snapshot_rows: list[dict[str, Any]] | None = None,
        evaluation_run_rows: list[dict[str, Any]] | None = None,
        evaluation_result_rows: list[dict[str, Any]] | None = None,
        retrieval_evaluation_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.run_rows = run_rows or []
        self.feedback_rows = feedback_rows or []
        self.answer_snapshot_rows = answer_snapshot_rows or []
        self.evaluation_run_rows = evaluation_run_rows or []
        self.evaluation_result_rows = evaluation_result_rows or []
        self.retrieval_evaluation_rows = retrieval_evaluation_rows or []
        self.executed: list[tuple[str, dict[str, Any] | None]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(
        self, statement: str, params: dict[str, Any] | None = None
    ) -> FakeCursor:
        self.executed.append((statement, params))
        if "FROM answer_snapshots" in statement:
            return FakeCursor(self.answer_snapshot_rows)
        if "FROM retrieval_evaluation_results" in statement:
            return FakeCursor(self.retrieval_evaluation_rows)
        if "FROM evaluation_results" in statement:
            return FakeCursor(self.evaluation_result_rows)
        if "FROM evaluation_runs" in statement:
            return FakeCursor(self.evaluation_run_rows)
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
    assert any(
        "CREATE TABLE IF NOT EXISTS answer_snapshots" in sql for sql in statements
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS evaluation_runs" in sql for sql in statements
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS evaluation_results" in sql for sql in statements
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS retrieval_evaluation_results" in sql
        for sql in statements
    )
    assert any("INSERT INTO retrieval_evaluation_results" in sql for sql in statements)
    assert any("monitoring_runs_session_id_idx" in sql for sql in statements)
    assert any("monitoring_runs_completed_at_idx" in sql for sql in statements)
    assert any("feedback_events_session_id_idx" in sql for sql in statements)
    assert any("answer_snapshots_session_id_idx" in sql for sql in statements)
    assert any("evaluation_results_request_id_idx" in sql for sql in statements)
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


def test_recording_store_persists_answer_snapshot() -> None:
    connection = FakeConnection()
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )
    snapshot = _answer_snapshot()

    store.record_answer_snapshot(snapshot)

    _statement, params = connection.executed[0]
    assert params is not None
    assert params["request_id"] == "request-1"
    assert params["session_id"] == "session-1"
    assert params["run_kind"] == "direct"
    assert params["question"] == "Where is target?"
    assert params["repository_name"] == "repo"
    assert params["question_mode"] == "locate"
    assert params["retrieval_mode"] == "dense"
    assert isinstance(params["answer"], Jsonb)
    assert params["answer"].obj["summary"] == "Target lives in src/example.py."
    assert isinstance(params["evidence"], Jsonb)
    assert params["evidence"].obj[0]["path"] == "src/example.py"


def test_recording_store_persists_evaluation_run_and_result() -> None:
    connection = FakeConnection()
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )
    started_at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    evaluation_run = EvaluationRunRecord(
        evaluation_run_id="eval-run-1",
        source_type=EvaluationSourceType.MONITORED_RUNS,
        source_label="latest monitored answers",
        judge_model="gpt-5.1",
        status=EvaluationRunStatus.RUNNING,
        started_at=started_at,
    )
    result = PersistedEvaluationResult(
        result_id="result-1",
        evaluation_run_id="eval-run-1",
        request_id="request-1",
        run_kind=RunKind.DIRECT,
        question="Where is target?",
        answer_correctness=None,
        faithfulness=5,
        citation_precision=5,
        reference_coverage=None,
        answer_relevance=4,
        presentation_quality=4,
        unsupported_claim_count=0,
        feedback_useful=1,
        feedback_not_useful=0,
        latency_ms_total=1000,
        total_estimated_cost_usd=Decimal("0.012"),
        notes="Grounded answer.",
        created_at=started_at,
    )

    store.record_evaluation_run(evaluation_run)
    store.record_evaluation_result(result)

    _run_statement, run_params = connection.executed[0]
    _result_statement, result_params = connection.executed[1]
    assert run_params is not None
    assert run_params["evaluation_run_id"] == "eval-run-1"
    assert run_params["source_type"] == "monitored_runs"
    assert run_params["status"] == "running"
    assert result_params is not None
    assert result_params["result_id"] == "result-1"
    assert result_params["request_id"] == "request-1"
    assert result_params["run_kind"] == "direct"
    assert result_params["answer_correctness"] is None
    assert result_params["faithfulness"] == 5
    assert result_params["feedback_useful"] == 1


def test_recording_store_lists_answer_snapshots_for_evaluation() -> None:
    answer = ResearchAnswer(
        question="Which modules change?",
        mode=RagMode.CHANGE,
        summary="Change src/example.py.",
        evidence=[
            EvidenceItem(
                evidence_id="E1",
                path="src/example.py",
                start_line=1,
                end_line=2,
                symbol="target",
                score=0.9,
                reason="Relevant implementation.",
            )
        ],
        confidence=0.8,
    )
    connection = FakeConnection(
        answer_snapshot_rows=[
            {
                "request_id": "request-1",
                "session_id": "session-1",
                "run_kind": "agentic",
                "question": "Which modules change?",
                "answer": answer.model_dump(mode="json"),
                "evidence": [item.model_dump(mode="json") for item in answer.evidence],
                "repository_id": "repo-id",
                "repository_name": "repo",
                "branch": "main",
                "commit_hash": "abc123",
                "question_mode": "change",
                "retrieval_mode": "dense",
                "retrieval_limit": 5,
                "created_at": datetime(2026, 8, 11, 12, tzinfo=UTC),
                "latency_ms_total": 1000,
                "total_estimated_cost_usd": Decimal("0.012"),
                "feedback_useful": 1,
                "feedback_not_useful": 2,
            }
        ]
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    snapshots = store.list_answer_snapshots_for_evaluation(
        limit=10,
        run_kind=RunKind.AGENTIC,
        repository_name="repo",
        request_ids=["request-1", "request-2"],
    )

    _statement, params = connection.executed[0]
    assert params == {
        "limit": 10,
        "run_kind": "agentic",
        "repository_name": "repo",
        "request_ids": ["request-1", "request-2"],
    }
    assert len(snapshots) == 1
    assert snapshots[0].request_id == "request-1"
    assert snapshots[0].run_kind is RunKind.AGENTIC
    assert isinstance(snapshots[0].answer, ResearchAnswer)
    assert snapshots[0].feedback_useful == 1
    assert snapshots[0].feedback_not_useful == 2
    assert snapshots[0].latency_ms_total == 1000
    assert snapshots[0].total_estimated_cost_usd == Decimal("0.012")


def test_recording_store_returns_evaluation_dashboard_data() -> None:
    started_at = datetime(2026, 8, 11, 12, tzinfo=UTC)
    connection = FakeConnection(
        evaluation_run_rows=[
            _evaluation_run_row(
                evaluation_run_id="eval-run-1",
                source_type="monitored_runs",
                status="completed",
                started_at=started_at,
            ),
            _evaluation_run_row(
                evaluation_run_id="eval-run-2",
                source_type="dataset",
                status="failed",
                started_at=datetime(2026, 8, 11, 11, tzinfo=UTC),
                error_message="judge failed",
            ),
        ],
        evaluation_result_rows=[
            _evaluation_result_row(
                result_id="result-1",
                evaluation_run_id="eval-run-1",
                source_type="monitored_runs",
                source_label="monitored-runs",
                run_kind="agentic",
                unsupported_claim_count=0,
                feedback_useful=1,
                latency_ms_total=1500,
            ),
            _evaluation_result_row(
                result_id="result-2",
                evaluation_run_id="eval-run-1",
                source_type="monitored_runs",
                source_label="monitored-runs",
                run_kind="direct",
                answer_correctness=None,
                faithfulness=4,
                citation_precision=4,
                reference_coverage=None,
                answer_relevance=3,
                presentation_quality=3,
                unsupported_claim_count=1,
                feedback_not_useful=1,
                latency_ms_total=800,
            ),
        ],
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    summary = store.evaluation_summary()
    runs = store.list_evaluation_runs(limit=10)
    results = store.list_evaluation_results(limit=10, run_kind=RunKind.AGENTIC)

    assert summary.total_runs == 2
    assert summary.completed_runs == 1
    assert summary.failed_runs == 1
    assert summary.total_results == 2
    assert summary.unsupported_claim_rate == 0.5
    metric_counts = {item.metric: item.result_count for item in summary.metric_averages}
    assert metric_counts["faithfulness"] == 2
    assert "answer_correctness" not in metric_counts
    assert [
        (item.run_kind, item.result_count) for item in summary.average_by_run_kind
    ] == [
        (RunKind.AGENTIC, 1),
        (RunKind.DIRECT, 1),
    ]
    assert [run.evaluation_run_id for run in runs.runs] == [
        "eval-run-1",
        "eval-run-2",
    ]
    assert runs.runs[0].result_count == 2
    assert runs.runs[0].unsupported_claim_count == 1
    assert [result.result_id for result in results.results] == ["result-1"]
    assert results.results[0].average_score == 5
    assert results.results[0].feedback_useful == 1
    assert results.results[0].answer_evidence[0].evidence_id == "E1"


def test_recording_store_returns_retrieval_evaluation_results() -> None:
    connection = FakeConnection(
        retrieval_evaluation_rows=[
            _retrieval_evaluation_row(dataset="Development", mode="dense"),
            _retrieval_evaluation_row(dataset="Held-out", mode="hybrid"),
            _retrieval_evaluation_row(dataset="Held-out", mode="dense", selected=True),
        ]
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    results = store.list_retrieval_evaluation_results()

    assert [(item.dataset, item.mode) for item in results.results] == [
        ("Held-out", RetrievalMode.DENSE),
        ("Held-out", RetrievalMode.HYBRID),
        ("Development", RetrievalMode.DENSE),
    ]
    assert results.results[0].selected is True
    assert results.results[0].file_hit_rate == 0.467


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


def test_recording_store_lists_monitoring_runs_with_feedback_counts() -> None:
    connection = FakeConnection(
        run_rows=[
            _run_row(
                request_id="request-1",
                run_kind="direct",
                completed_at=datetime(2026, 8, 7, 12, 0, 1, tzinfo=UTC),
            ),
            _run_row(
                request_id="request-2",
                run_kind="agentic",
                completed_at=datetime(2026, 8, 7, 12, 0, 2, tzinfo=UTC),
                error_type="ResearchBudgetExceeded",
                tool_call_count=4,
            ),
        ],
        feedback_rows=[
            _feedback_row("feedback-1", "request-2", useful=False),
            _feedback_row("feedback-2", "request-2", useful=True),
        ],
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    runs = store.list_monitoring_runs(limit=10)

    assert [run.request_id for run in runs.runs] == ["request-2", "request-1"]
    assert runs.runs[0].run_kind == RunKind.AGENTIC
    assert runs.runs[0].has_error is True
    assert runs.runs[0].tool_call_count == 4
    assert runs.runs[0].feedback_useful == 1
    assert runs.runs[0].feedback_not_useful == 1


def test_recording_store_filters_monitoring_runs() -> None:
    connection = FakeConnection(
        run_rows=[
            _run_row(request_id="request-1", run_kind="direct"),
            _run_row(
                request_id="request-2",
                run_kind="agentic",
                repository_name="other-repo",
                error_type="ResearchBudgetExceeded",
            ),
        ],
        feedback_rows=[_feedback_row("feedback-1", "request-2", useful=False)],
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    runs = store.list_monitoring_runs(
        limit=10,
        run_kind=RunKind.AGENTIC,
        repository_name="other",
        has_error=True,
        feedback=MonitoringFeedbackFilter.NOT_USEFUL,
    )

    assert [run.request_id for run in runs.runs] == ["request-2"]


def test_recording_store_returns_monitoring_run_detail() -> None:
    connection = FakeConnection(
        run_rows=[
            _run_row(
                request_id="request-1",
                error_type="OpenAIError",
                error_message="Missing credentials",
            )
        ],
        feedback_rows=[_feedback_row("feedback-1", "request-1", useful=False)],
    )
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    detail = store.get_monitoring_run("request-1")

    assert detail is not None
    assert detail.request_id == "request-1"
    assert detail.repository_id == "repo-id"
    assert detail.error_type == "OpenAIError"
    assert detail.error_message == "Missing credentials"
    assert detail.model_usage[0].model == "gpt-5-mini"
    assert detail.feedback_events[0].comment == "Needs clearer targets."


def test_recording_store_returns_none_for_missing_monitoring_run() -> None:
    connection = FakeConnection(run_rows=[_run_row(request_id="request-1")])
    store = PostgresRecordingStore(
        "postgresql://example", FakeConnectionFactory(connection)
    )

    assert store.get_monitoring_run("missing") is None


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


def _answer_snapshot() -> AnswerSnapshot:
    evidence = EvidenceItem(
        evidence_id="E1",
        path="src/example.py",
        start_line=1,
        end_line=2,
        symbol="target",
        score=0.9,
        reason="Relevant implementation.",
    )
    return AnswerSnapshot(
        request_id="request-1",
        session_id="session-1",
        run_kind=RunKind.DIRECT,
        question="Where is target?",
        answer=RagAnswer(
            question="Where is target?",
            mode=RagMode.LOCATE,
            summary="Target lives in src/example.py.",
            evidence=[evidence],
            relevant_files=["src/example.py"],
            relevant_symbols=["target"],
            confidence=0.9,
        ),
        evidence=[evidence],
        repository_id="repo-id",
        repository_name="repo",
        branch="main",
        commit_hash="abc123",
        question_mode=RagMode.LOCATE,
        retrieval_mode=RetrievalMode.DENSE,
        retrieval_limit=5,
        created_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )


def _run_row(
    *,
    request_id: str,
    run_kind: str = "direct",
    repository_name: str = "repo",
    completed_at: datetime | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    tool_call_count: int = 0,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "session_id": "session-1",
        "run_kind": run_kind,
        "started_at": datetime(2026, 8, 7, 12, tzinfo=UTC),
        "completed_at": completed_at or datetime(2026, 8, 7, 12, 0, 1, tzinfo=UTC),
        "repository_id": "repo-id",
        "repository_name": repository_name,
        "branch": "main",
        "commit_hash": "abc123",
        "question_mode": "change",
        "retrieval_mode": "hybrid",
        "retrieval_limit": 5,
        "retrieved_chunk_count": 3,
        "unique_file_count": 2,
        "evidence_count": 2,
        "latency_ms_total": 1000,
        "latency_ms_retrieval": 200,
        "latency_ms_model": 800,
        "tool_call_count": tool_call_count,
        "insufficient_evidence": False,
        "error_type": error_type,
        "error_message": error_message,
        "total_estimated_cost_usd": Decimal("0.012"),
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
    }


def _feedback_row(
    feedback_id: str,
    request_id: str | None,
    *,
    useful: bool,
) -> dict[str, Any]:
    return {
        "feedback_id": feedback_id,
        "session_id": "session-1",
        "request_id": request_id,
        "useful": useful,
        "comment": "Needs clearer targets.",
        "submitted_at": datetime(2026, 8, 7, 12, 5, tzinfo=UTC),
    }


def _evaluation_run_row(
    *,
    evaluation_run_id: str,
    source_type: str,
    status: str,
    started_at: datetime,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "evaluation_run_id": evaluation_run_id,
        "source_type": source_type,
        "source_label": "monitored-runs"
        if source_type == "monitored_runs"
        else "eval/held_out.json",
        "judge_model": "gpt-5.1",
        "status": status,
        "started_at": started_at,
        "completed_at": started_at,
        "error_message": error_message,
    }


def _evaluation_result_row(
    *,
    result_id: str,
    evaluation_run_id: str,
    source_type: str,
    source_label: str,
    run_kind: str | None,
    answer_correctness: int | None = None,
    faithfulness: int = 5,
    citation_precision: int = 5,
    reference_coverage: int | None = None,
    answer_relevance: int = 5,
    presentation_quality: int = 5,
    unsupported_claim_count: int = 0,
    feedback_useful: int = 0,
    feedback_not_useful: int = 0,
    latency_ms_total: int | None = None,
) -> dict[str, Any]:
    return {
        "result_id": result_id,
        "evaluation_run_id": evaluation_run_id,
        "source_type": source_type,
        "source_label": source_label,
        "repository_name": "repo_deep_research"
        if source_type == "monitored_runs"
        else None,
        "branch": "dev" if source_type == "monitored_runs" else None,
        "commit_hash": "abc123" if source_type == "monitored_runs" else None,
        "record_id": "record-1",
        "request_id": "request-1",
        "run_kind": run_kind,
        "question": "Where is target?",
        "answer_correctness": answer_correctness,
        "faithfulness": faithfulness,
        "citation_precision": citation_precision,
        "reference_coverage": reference_coverage,
        "answer_relevance": answer_relevance,
        "presentation_quality": presentation_quality,
        "unsupported_claim_count": unsupported_claim_count,
        "feedback_useful": feedback_useful,
        "feedback_not_useful": feedback_not_useful,
        "latency_ms_total": latency_ms_total,
        "total_estimated_cost_usd": Decimal("0.012"),
        "notes": "Grounded.",
        "answer_evidence": [
            {
                "evidence_id": "E1",
                "path": "src/example.py",
                "start_line": 1,
                "end_line": 2,
                "symbol": "target",
                "score": 0.9,
                "reason": "Relevant implementation.",
                "content": "def target(): ...",
            }
        ],
        "created_at": datetime(2026, 8, 11, 12, tzinfo=UTC),
    }


def _retrieval_evaluation_row(
    *,
    dataset: str,
    mode: str,
    selected: bool = False,
) -> dict[str, Any]:
    dataset_path = dataset.lower().replace("-", "_")
    return {
        "dataset": dataset,
        "mode": mode,
        "source_label": f"eval/{dataset_path}.json local alpha smoke",
        "limit_value": 5,
        "record_count": 15,
        "file_hit_rate": Decimal("0.467") if selected else Decimal("0.400"),
        "file_mrr": Decimal("0.313") if selected else Decimal("0.261"),
        "file_recall": Decimal("0.311") if selected else Decimal("0.278"),
        "file_precision": Decimal("0.200") if selected else Decimal("0.103"),
        "symbol_hit_rate": Decimal("0.400") if selected else Decimal("0.333"),
        "selected": selected,
        "measured_at": datetime(2026, 8, 13, tzinfo=UTC),
    }
