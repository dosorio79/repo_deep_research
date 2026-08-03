"""Tests for grounded direct-RAG behavior."""

from decimal import Decimal
from pathlib import Path

from repo_research.models import (
    AnswerEvaluationResult,
    EvaluationRecord,
    ModelUsage,
    ParsedChunk,
    RagMode,
    RagRequest,
    RepositoryIdentity,
    RetrievalMode,
    SearchResult,
)
from repo_research.rag import (
    AnswerGenerationResult,
    ChangeTargetDraft,
    DirectRagService,
    EvidenceReference,
    RagAnswerDraft,
    _model_usage_from_response,
    evaluate_answers,
    infer_rag_mode,
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

    def __init__(self, draft: RagAnswerDraft, usage: ModelUsage | None = None) -> None:
        self._draft = draft
        self._usage = usage

    def generate_answer(
        self,
        *,
        request: RagRequest,
        evidence_context: str,
    ) -> AnswerGenerationResult:
        assert request.question
        assert evidence_context
        return AnswerGenerationResult(draft=self._draft, usage=self._usage)


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


class FakeUsageDetails:
    """Minimal nested usage details object for response telemetry tests."""

    def __init__(
        self,
        *,
        cached_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> None:
        self.cached_tokens = cached_tokens
        self.reasoning_tokens = reasoning_tokens


class FakeResponseUsage:
    """Minimal Responses API usage object for telemetry tests."""

    def __init__(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cached_tokens: int | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.input_tokens_details = FakeUsageDetails(cached_tokens=cached_tokens)
        self.output_tokens_details = FakeUsageDetails(reasoning_tokens=None)


class FakeResponse:
    """Minimal Responses API response object for telemetry tests."""

    def __init__(self, usage: FakeResponseUsage) -> None:
        self.usage = usage


class TelemetryGenerator:
    """Return a valid draft with usage telemetry extracted from a fake response."""

    def __init__(self, draft: RagAnswerDraft, response: FakeResponse) -> None:
        self._draft = draft
        self._response = response

    def generate_answer(
        self,
        *,
        request: RagRequest,
        evidence_context: str,
    ) -> AnswerGenerationResult:
        assert request.question
        assert evidence_context
        return AnswerGenerationResult(
            draft=self._draft,
            usage=_model_usage_from_response(
                model="gpt-5-mini",
                response=self._response,
            ),
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


def test_rag_run_returns_trace_with_usage_and_price(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    chunk = _chunk(repository)
    service = DirectRagService(
        database=FakeDatabase([SearchResult(chunk=chunk, score=0.9)]),
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Configuration is validated in Settings.",
                evidence=[
                    EvidenceReference(
                        evidence_id="E1", reason="Defines validated settings."
                    )
                ],
                confidence=0.8,
            ),
            usage=ModelUsage(
                provider="openai",
                model="gpt-5-mini",
                input_tokens=1000,
                output_tokens=200,
                total_tokens=1200,
                cached_input_tokens=0,
                estimated_cost_usd=Decimal("0.00065"),
                pricing_source="test",
                pricing_version="test",
            ),
        ),
    )

    run = service.run(
        repository=repository,
        request=RagRequest(
            question="Where is configuration validated?",
            mode=RagMode.LOCATE,
        ),
    )

    assert run.answer.insufficient_evidence is False
    assert run.trace.repository_id == repository.repository_id
    assert run.trace.question_mode is RagMode.LOCATE
    assert run.trace.retrieved_chunk_count == 1
    assert run.trace.unique_file_count == 1
    assert run.trace.evidence_ids == ["E1"]
    assert run.trace.tool_call_count == 0
    assert run.trace.model_usage[0].model == "gpt-5-mini"
    assert run.trace.total_estimated_cost_usd == Decimal("0.00065")


def test_rag_run_keeps_valid_answer_when_pricing_estimation_fails(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    chunk = _chunk(repository)
    service = DirectRagService(
        database=FakeDatabase([SearchResult(chunk=chunk, score=0.9)]),
        generator=TelemetryGenerator(
            RagAnswerDraft(
                summary="Configuration is validated in Settings.",
                evidence=[
                    EvidenceReference(
                        evidence_id="E1", reason="Defines validated settings."
                    )
                ],
                confidence=0.8,
            ),
            response=FakeResponse(
                usage=FakeResponseUsage(
                    input_tokens=10,
                    cached_tokens=20,
                    output_tokens=5,
                    total_tokens=15,
                )
            ),
        ),
    )

    run = service.run(
        repository=repository,
        request=RagRequest(
            question="Where is configuration validated?",
            mode=RagMode.LOCATE,
        ),
    )

    assert run.answer.insufficient_evidence is False
    assert run.trace.model_usage[0].cached_input_tokens == 20
    assert run.trace.model_usage[0].estimated_cost_usd is None
    assert run.trace.model_usage[0].pricing_source == "unknown"
    assert run.trace.total_estimated_cost_usd is None


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
    assert answer.evidence[0].path == "src/repo_research/config.py"
    assert answer.relevant_files == ["src/repo_research/config.py"]
    assert answer.relevant_symbols == ["Settings"]
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


def test_rag_run_traces_empty_retrieval(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = DirectRagService(
        database=FakeDatabase([]),
        generator=FakeGenerator(
            RagAnswerDraft(summary="Should not be used.", confidence=0.1)
        ),
    )

    run = service.run(
        repository=repository,
        request=RagRequest(question="Where is missing logic?"),
    )

    assert run.answer.insufficient_evidence is True
    assert run.trace.insufficient_evidence is True
    assert run.trace.retrieved_chunk_count == 0
    assert run.trace.unique_file_count == 0
    assert run.trace.model_usage == []
    assert run.trace.error_type is None


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


def test_auto_mode_infers_locate_for_where_questions(tmp_path: Path) -> None:
    request = RagRequest(question="where is repository configuration validated?")

    assert infer_rag_mode(request) is RagMode.LOCATE


def test_auto_mode_infers_change_for_change_impact_questions(tmp_path: Path) -> None:
    assert infer_rag_mode(RagRequest(question="Add a cross-encoder reranker")) is (
        RagMode.CHANGE
    )
    assert infer_rag_mode(RagRequest(question="What should I add?")) is RagMode.CHANGE
    assert infer_rag_mode(RagRequest(question="How to modify retrieval?")) is (
        RagMode.CHANGE
    )


def test_locate_mode_removes_change_targets_and_metadata_prompts(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    service = DirectRagService(
        database=FakeDatabase(
            [SearchResult(chunk=_chunk(repository, symbol="Settings"), score=0.9)]
        ),
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Configuration is validated in Settings.",
                evidence=[
                    EvidenceReference(
                        evidence_id="E1",
                        reason="Defines the settings validation boundary.",
                    )
                ],
                change_targets=[
                    ChangeTargetDraft(
                        reason="Add tests.",
                        evidence_ids=["E1"],
                    )
                ],
                unresolved_questions=[
                    "Do you want an exact file path or line reference?",
                    "The evidence does not show deployment overrides.",
                ],
                confidence=0.8,
            )
        ),
    )

    answer = service.answer(
        repository=repository,
        request=RagRequest(question="where is repository configuration validated?"),
    )

    assert answer.mode is RagMode.LOCATE
    assert answer.change_targets == []
    assert answer.unresolved_questions == [
        "The evidence does not show deployment overrides."
    ]


def test_change_mode_keeps_change_targets(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = DirectRagService(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        generator=FakeGenerator(
            RagAnswerDraft(
                summary="Update Settings.",
                evidence=[
                    EvidenceReference(
                        evidence_id="E1",
                        reason="Defines the settings validation boundary.",
                    )
                ],
                change_targets=[
                    ChangeTargetDraft(reason="Add a new setting.", evidence_ids=["E1"])
                ],
                confidence=0.8,
            )
        ),
    )

    answer = service.answer(
        repository=repository,
        request=RagRequest(
            question="which files should change to add a new setting?",
            mode=RagMode.CHANGE,
        ),
    )

    assert answer.change_targets[0].path == "src/repo_research/config.py"


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
