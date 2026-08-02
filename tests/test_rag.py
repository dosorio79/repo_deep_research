"""Tests for grounded direct-RAG behavior."""

from pathlib import Path

from repo_research.models import (
    AnswerEvaluationResult,
    EvaluationRecord,
    ParsedChunk,
    RagMode,
    RagRequest,
    RepositoryIdentity,
    RetrievalMode,
    SearchResult,
)
from repo_research.rag import (
    DirectRagService,
    EvidenceReference,
    RagAnswerDraft,
    evaluate_answers,
    write_answer_evaluation_report,
)


class FakeDatabase:
    """Return fixed retrieval results for deterministic RAG tests."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.queries: list[object] = []

    def search(self, query: object) -> list[SearchResult]:
        self.queries.append(query)
        return self._results


class FakeGenerator:
    """Return a fixed model draft without network calls."""

    def __init__(self, draft: RagAnswerDraft) -> None:
        self._draft = draft

    def generate_answer(
        self,
        *,
        request: RagRequest,
        evidence_context: str,
    ) -> RagAnswerDraft:
        assert request.question
        assert evidence_context
        return self._draft


class FakeJudge:
    """Return deterministic judge scores without model calls."""

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: object,
    ) -> AnswerEvaluationResult:
        return AnswerEvaluationResult(
            record_id=record.id,
            question=record.question,
            correctness=4,
            groundedness=5,
            citation_accuracy=5,
            completeness=4,
            usefulness=4,
            unsupported_claim_count=0,
        )


def test_rag_maps_evidence_ids_to_canonical_citations(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    chunk = _chunk(repository)
    service = DirectRagService(
        database=FakeDatabase([SearchResult(chunk=chunk, score=0.9)]),
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Configuration is validated in Settings.",
                implementation_flow=["Settings loads environment values."],
                evidence=[
                    EvidenceReference(
                        evidence_id="E1", reason="Defines validated settings."
                    )
                ],
                confidence=0.8,
            )
        ),
    )

    answer = service.answer(
        repository=repository,
        request=RagRequest(
            question="Where is configuration validated?",
            mode=RagMode.LOCATE,
        ),
    )

    assert answer.insufficient_evidence is False
    assert answer.evidence[0].path == "src/repo_research/config.py"
    assert answer.evidence[0].start_line == 1
    assert answer.relevant_files == ["src/repo_research/config.py"]
    assert answer.relevant_symbols == ["Settings"]


def test_rag_rejects_unknown_model_evidence_ids(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = DirectRagService(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Unsupported claim.",
                evidence=[EvidenceReference(evidence_id="E99", reason="Missing.")],
                confidence=0.5,
            )
        ),
    )

    answer = service.answer(
        repository=repository,
        request=RagRequest(question="Where is configuration validated?"),
    )

    assert answer.insufficient_evidence is True
    assert "unknown evidence IDs" in answer.unresolved_questions[0]


def test_rag_returns_insufficient_evidence_without_results(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = DirectRagService(
        database=FakeDatabase([]),
        generator=FakeGenerator(
            RagAnswerDraft(summary="Should not be used.", confidence=0.1)
        ),
    )

    answer = service.answer(
        repository=repository,
        request=RagRequest(question="Where is missing logic?"),
    )

    assert answer.insufficient_evidence is True
    assert answer.evidence == []


def test_rag_preserves_selected_retrieval_order(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    database = FakeDatabase(
        [
            SearchResult(
                chunk=_chunk(
                    repository,
                    path="README.md",
                    symbol="Quick start",
                ),
                score=0.79,
            ),
            SearchResult(
                chunk=_chunk(
                    repository,
                    path="tests/test_config.py",
                    symbol="test_settings_reject_invalid_qdrant_url",
                ),
                score=0.74,
            ),
            SearchResult(
                chunk=_chunk(
                    repository,
                    path="src/repo_research/config.py",
                    symbol="Settings",
                ),
                score=0.72,
            ),
        ]
    )
    service = DirectRagService(
        database=database,
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Configuration is validated in Settings.",
                evidence=[
                    EvidenceReference(
                        evidence_id="E1", reason="Defines validated settings."
                    )
                ],
                confidence=0.8,
            )
        ),
    )

    answer = service.answer(
        repository=repository,
        request=RagRequest(
            question="Where is configuration validated?",
            mode=RagMode.LOCATE,
            limit=1,
        ),
    )

    assert answer.evidence[0].path == "README.md"
    assert answer.relevant_symbols == ["Quick start"]


def test_answer_evaluation_writes_stable_report(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = DirectRagService(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Configuration is validated in Settings.",
                evidence=[
                    EvidenceReference(
                        evidence_id="E1", reason="Defines validated settings."
                    )
                ],
                confidence=0.8,
            )
        ),
    )
    records = [
        EvaluationRecord(
            id="locate_001",
            question="Where is configuration validated?",
            question_type="locate",
            relevant_files=["src/repo_research/config.py"],
            relevant_symbols=["Settings"],
        )
    ]

    results = evaluate_answers(
        service=service,
        judge=FakeJudge(),
        repository=repository,
        records=records,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
    )
    report = tmp_path / "answer-report.json"
    write_answer_evaluation_report(results, report)

    assert results[0].record_id == "locate_001"
    assert '"citation_accuracy": 5.0' in report.read_text(encoding="utf-8")


def _repository(root: Path) -> RepositoryIdentity:
    return RepositoryIdentity(
        name="sample",
        root_path=root,
        branch="main",
        commit_hash="abc123",
    )


def _chunk(
    repository: RepositoryIdentity,
    *,
    path: str = "src/repo_research/config.py",
    symbol: str | None = "Settings",
) -> ParsedChunk:
    return ParsedChunk(
        chunk_id="chunk-1",
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        path=path,
        language="python",
        chunk_type="class",
        symbol=symbol,
        start_line=1,
        end_line=5,
        content="class Settings(BaseSettings):\n    pass\n",
        content_hash="hash",
    )
