"""Tests for typed repository-evidence models."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from repo_research.models import (
    AnswerEvaluationResult,
    ChangeTarget,
    EvidenceItem,
    RagMode,
    RagRunTrace,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchBudget,
    ResearchRequest,
    ResearchRunResult,
    ResearchStep,
    RetrievalMode,
    create_chunk,
)


def test_create_chunk_is_deterministic_for_identical_source() -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=Path("/tmp/sample"),
        branch="main",
        commit_hash="abc123",
    )

    first = create_chunk(
        repository=repository,
        path="module.py",
        language="python",
        chunk_type="function",
        symbol="work",
        start_line=1,
        end_line=2,
        content="def work():\n    return 1\n",
    )
    second = create_chunk(
        repository=repository,
        path="module.py",
        language="python",
        chunk_type="function",
        symbol="work",
        start_line=1,
        end_line=2,
        content="def work():\n    return 1\n",
    )

    assert first.chunk_id == second.chunk_id
    assert first.content_hash == second.content_hash


def test_create_chunk_rejects_reversed_line_ranges() -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=Path("/tmp/sample"),
        branch="main",
        commit_hash="abc123",
    )

    with pytest.raises(ValidationError, match="end_line"):
        create_chunk(
            repository=repository,
            path="module.py",
            language="python",
            chunk_type="function",
            start_line=2,
            end_line=1,
            content="x = 1\n",
        )


def test_answer_evaluation_scores_are_bounded() -> None:
    with pytest.raises(ValidationError, match="citation_accuracy"):
        AnswerEvaluationResult(
            record_id="locate_001",
            question="Where is configuration validated?",
            correctness=4,
            groundedness=4,
            citation_accuracy=6,
            completeness=4,
            usefulness=4,
            unsupported_claim_count=0,
        )


def test_research_request_uses_bounded_change_defaults() -> None:
    request = ResearchRequest(question="Which modules change for M4?")

    assert request.mode is RagMode.CHANGE
    assert request.retrieval_mode is RetrievalMode.DENSE
    assert request.retrieval_limit == 5
    assert request.budget == ResearchBudget(
        max_searches=3,
        max_file_reads=5,
        max_total_tool_calls=8,
    )


def test_research_budget_rejects_total_below_per_tool_bounds() -> None:
    with pytest.raises(ValidationError, match="max_searches"):
        ResearchBudget(max_searches=4, max_file_reads=2, max_total_tool_calls=3)

    with pytest.raises(ValidationError, match="max_file_reads"):
        ResearchBudget(max_searches=2, max_file_reads=4, max_total_tool_calls=3)


def test_research_run_result_reuses_trace_contract() -> None:
    answer = ResearchAnswer(
        question="Which modules change for bounded research?",
        summary="Add a bounded research service over the retrieval boundary.",
        research_steps=[
            ResearchStep(
                sequence=1,
                action="search_repository",
                rationale="Find current direct-RAG contracts.",
                evidence_ids=["E1"],
            )
        ],
        evidence=[
            EvidenceItem(
                evidence_id="E1",
                path="src/repo_research/rag.py",
                start_line=1,
                end_line=10,
                symbol="DirectRagService",
                score=0.9,
                reason="Defines the existing direct-RAG service boundary.",
            )
        ],
        relevant_files=["src/repo_research/rag.py"],
        relevant_symbols=["DirectRagService"],
        change_targets=[
            ChangeTarget(
                path="src/repo_research/research.py",
                symbol=None,
                reason="Add the M4 service next to direct RAG.",
                evidence_ids=["E1"],
            )
        ],
        confidence=0.8,
    )
    trace = RagRunTrace(
        request_id="test-request",
        started_at=datetime(2026, 8, 3, tzinfo=UTC),
        completed_at=datetime(2026, 8, 3, 0, 0, 1, tzinfo=UTC),
        repository_id="repo",
        repository_name="repo_deep_research",
        branch="feat/m4-agentic-research-tools",
        commit_hash="abc123",
        question_mode=RagMode.CHANGE,
        retrieval_mode=RetrievalMode.DENSE,
        retrieval_limit=5,
        retrieved_chunk_count=1,
        unique_file_count=1,
        evidence_ids=["E1"],
        latency_ms_total=1000,
        latency_ms_retrieval=100,
        tool_call_count=1,
    )

    result = ResearchRunResult(answer=answer, trace=trace)

    assert result.answer.research_steps[0].action == "search_repository"
    assert result.trace.tool_call_count == 1


def test_research_answer_rejects_unknown_step_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="unknown evidence IDs"):
        ResearchAnswer(
            question="Which modules change for bounded research?",
            summary="A step cannot cite evidence that is not returned.",
            research_steps=[
                ResearchStep(
                    sequence=1,
                    action="search_repository",
                    rationale="Find current direct-RAG contracts.",
                    evidence_ids=["E99"],
                )
            ],
            confidence=0.0,
        )


def test_research_answer_rejects_unknown_change_target_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="unknown evidence IDs"):
        ResearchAnswer(
            question="Which modules change for bounded research?",
            summary="A change target cannot cite evidence that is not returned.",
            change_targets=[
                ChangeTarget(
                    path="src/repo_research/research.py",
                    symbol=None,
                    reason="Add the M4 service next to direct RAG.",
                    evidence_ids=["E99"],
                )
            ],
            confidence=0.0,
        )
