"""Tests for typed repository-evidence models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from repo_research.models import (
    AnswerEvaluationResult,
    RepositoryIdentity,
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
