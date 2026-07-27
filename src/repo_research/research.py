"""Grounded direct-RAG research and answer evaluation services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from repo_research.evaluation import load_records
from repo_research.models import (
    AnswerEvaluationResult,
    ChangeTarget,
    EvaluationRecord,
    EvidenceItem,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchMode,
    ResearchRequest,
    RetrievalMode,
    SearchQuery,
    SearchResult,
)


class RepositorySearcher(Protocol):
    """The repository retrieval dependency used by direct RAG."""

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Return typed repository evidence for one query."""


class AnswerGenerator(Protocol):
    """Model adapter for generating a structured direct-RAG draft."""

    def generate_answer(
        self,
        *,
        request: ResearchRequest,
        evidence_context: str,
    ) -> ResearchAnswerDraft:
        """Return a model draft that cites opaque evidence IDs only."""


class AnswerJudge(Protocol):
    """Model adapter for judging a grounded answer against a record."""

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: ResearchAnswer,
    ) -> AnswerEvaluationResult:
        """Return judge scores for one answer."""


class EvidenceReference(BaseModel):
    """A model-selected evidence ID and relevance reason."""

    evidence_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ChangeTargetDraft(BaseModel):
    """A model-proposed change target grounded only by evidence IDs."""

    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ResearchAnswerDraft(BaseModel):
    """Structured model output before canonical citation validation."""

    summary: str = Field(min_length=1)
    implementation_flow: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    change_targets: list[ChangeTargetDraft] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class ResearchService:
    """Answer repository questions using one retrieval pass and grounded citations."""

    def __init__(
        self,
        *,
        database: RepositorySearcher,
        generator: AnswerGenerator,
    ) -> None:
        self._database = database
        self._generator = generator

    def research(
        self,
        *,
        repository: RepositoryIdentity,
        request: ResearchRequest,
    ) -> ResearchAnswer:
        """Return a direct-RAG answer with citations validated against retrieval."""
        results = self._database.search(
            SearchQuery(
                text=request.question,
                repository_id=repository.repository_id,
                commit_hash=repository.commit_hash,
                limit=request.limit,
                mode=request.retrieval_mode,
            )
        )
        if not results:
            return insufficient_evidence_answer(
                request=request,
                reason="No repository evidence was retrieved for the question.",
            )

        evidence_by_id = _evidence_by_id(results)
        evidence_context = _format_evidence_context(evidence_by_id, results)
        try:
            draft = self._generator.generate_answer(
                request=request,
                evidence_context=evidence_context,
            )
        except ValueError as error:
            return insufficient_evidence_answer(
                request=request,
                reason=f"Answer generation failed validation: {error}",
            )

        return _build_validated_answer(
            request=request,
            draft=draft,
            evidence_by_id=evidence_by_id,
        )


class OpenAIResponsesModel:
    """OpenAI Responses API adapter for direct answers and judge evaluation."""

    def __init__(self, *, answer_model: str, judge_model: str | None = None) -> None:
        self._answer_model = answer_model
        self._judge_model = judge_model or answer_model
        self._client = OpenAI()

    def generate_answer(
        self,
        *,
        request: ResearchRequest,
        evidence_context: str,
    ) -> ResearchAnswerDraft:
        """Generate a structured answer draft with the configured answer model."""
        prompt = _answer_prompt(request=request, evidence_context=evidence_context)
        return _create_structured_response(
            client=self._client,
            model=self._answer_model,
            prompt=prompt,
            response_model=ResearchAnswerDraft,
        )

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: ResearchAnswer,
    ) -> AnswerEvaluationResult:
        """Judge one answer using the configured judge model."""
        prompt = _judge_prompt(record=record, answer=answer)
        result = _create_structured_response(
            client=self._client,
            model=self._judge_model,
            prompt=prompt,
            response_model=AnswerEvaluationResult,
        )
        if result.record_id != record.id:
            raise ValueError("judge returned a record_id that does not match input")
        return result


def evaluate_answers(
    *,
    service: ResearchService,
    judge: AnswerJudge,
    repository: RepositoryIdentity,
    records: list[EvaluationRecord],
    retrieval_mode: RetrievalMode,
    limit: int,
) -> list[AnswerEvaluationResult]:
    """Run direct RAG and judge evaluation for versioned records."""
    results: list[AnswerEvaluationResult] = []
    for record in records:
        answer = service.research(
            repository=repository,
            request=ResearchRequest(
                question=record.question,
                mode=_research_mode_from_question_type(record.question_type),
                retrieval_mode=retrieval_mode,
                limit=limit,
            ),
        )
        results.append(judge.judge_answer(record=record, answer=answer))
    return results


def evaluate_answers_from_dataset(
    *,
    service: ResearchService,
    judge: AnswerJudge,
    repository: RepositoryIdentity,
    dataset: Path,
    retrieval_mode: RetrievalMode,
    limit: int,
) -> list[AnswerEvaluationResult]:
    """Load a dataset and evaluate answer quality."""
    return evaluate_answers(
        service=service,
        judge=judge,
        repository=repository,
        records=load_records(dataset),
        retrieval_mode=retrieval_mode,
        limit=limit,
    )


def write_answer_evaluation_report(
    results: list[AnswerEvaluationResult], path: Path
) -> None:
    """Write stable answer-evaluation JSON output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([result.model_dump(mode="json") for result in results], indent=2)
        + "\n",
        encoding="utf-8",
    )


def insufficient_evidence_answer(
    *,
    request: ResearchRequest,
    reason: str,
) -> ResearchAnswer:
    """Return a deterministic answer when evidence or validation is insufficient."""
    return ResearchAnswer(
        question=request.question,
        mode=request.mode,
        summary="Insufficient repository evidence to answer the question.",
        implementation_flow=[],
        evidence=[],
        relevant_files=[],
        relevant_symbols=[],
        change_targets=[],
        risks=["The answer is intentionally withheld because grounding failed."],
        confidence=0.0,
        unresolved_questions=[reason],
        insufficient_evidence=True,
    )


def _build_validated_answer(
    *,
    request: ResearchRequest,
    draft: ResearchAnswerDraft,
    evidence_by_id: dict[str, EvidenceItem],
) -> ResearchAnswer:
    referenced_ids = [reference.evidence_id for reference in draft.evidence]
    if not referenced_ids and not draft.insufficient_evidence:
        return insufficient_evidence_answer(
            request=request,
            reason="Model returned an answer without citing retrieved evidence.",
        )
    unknown_ids = sorted(
        {
            evidence_id
            for evidence_id in referenced_ids
            if evidence_id not in evidence_by_id
        }
    )
    for target in draft.change_targets:
        unknown_ids.extend(
            evidence_id
            for evidence_id in target.evidence_ids
            if evidence_id not in evidence_by_id
        )
    if unknown_ids:
        return insufficient_evidence_answer(
            request=request,
            reason=f"Model cited unknown evidence IDs: {sorted(set(unknown_ids))}",
        )

    evidence = [
        evidence_by_id[reference.evidence_id].model_copy(
            update={"reason": reference.reason}
        )
        for reference in draft.evidence
    ]
    relevant_files = sorted({item.path for item in evidence})
    relevant_symbols = sorted({item.symbol for item in evidence if item.symbol})
    change_targets = _canonical_change_targets(draft.change_targets, evidence_by_id)
    return ResearchAnswer(
        question=request.question,
        mode=request.mode,
        summary=draft.summary,
        implementation_flow=draft.implementation_flow,
        evidence=evidence,
        relevant_files=relevant_files,
        relevant_symbols=relevant_symbols,
        change_targets=change_targets,
        risks=draft.risks,
        confidence=draft.confidence,
        unresolved_questions=draft.unresolved_questions,
        insufficient_evidence=draft.insufficient_evidence,
    )


def _canonical_change_targets(
    targets: list[ChangeTargetDraft],
    evidence_by_id: dict[str, EvidenceItem],
) -> list[ChangeTarget]:
    canonical: list[ChangeTarget] = []
    for target in targets:
        first_evidence = evidence_by_id[target.evidence_ids[0]]
        canonical.append(
            ChangeTarget(
                path=first_evidence.path,
                symbol=first_evidence.symbol,
                reason=target.reason,
                evidence_ids=target.evidence_ids,
            )
        )
    return canonical


def _evidence_by_id(results: list[SearchResult]) -> dict[str, EvidenceItem]:
    evidence: dict[str, EvidenceItem] = {}
    for position, result in enumerate(results, start=1):
        chunk = result.chunk
        evidence_id = f"E{position}"
        evidence[evidence_id] = EvidenceItem(
            evidence_id=evidence_id,
            path=chunk.path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            symbol=chunk.symbol,
            score=result.score,
            reason="Retrieved repository evidence.",
        )
    return evidence


def _format_evidence_context(
    evidence_by_id: dict[str, EvidenceItem],
    results: list[SearchResult],
) -> str:
    sections: list[str] = []
    for evidence_id, result in zip(evidence_by_id, results, strict=True):
        item = evidence_by_id[evidence_id]
        symbol = item.symbol or "None"
        sections.append(
            "\n".join(
                [
                    f"[{evidence_id}] {item.path}:{item.start_line}-{item.end_line}",
                    f"symbol: {symbol}",
                    f"score: {item.score}",
                    "content:",
                    result.chunk.content,
                ]
            )
        )
    return "\n\n".join(sections)


def _answer_prompt(*, request: ResearchRequest, evidence_context: str) -> str:
    return "\n\n".join(
        [
            "You answer questions about a Python repository using only the provided "
            "evidence. Cite evidence by evidence_id only. Do not emit source paths "
            "or line numbers; the application maps evidence IDs to canonical "
            "citations. If the evidence is insufficient, set insufficient_evidence "
            "to true and explain what is missing.",
            f"Research mode: {request.mode.value}",
            f"Question: {request.question}",
            "Evidence:",
            evidence_context,
        ]
    )


def _judge_prompt(*, record: EvaluationRecord, answer: ResearchAnswer) -> str:
    return "\n\n".join(
        [
            "Judge this repository answer against the manually verified record. "
            "Score correctness, groundedness, citation_accuracy, completeness, "
            "and usefulness from 0 to 5. Count unsupported claims.",
            f"Record ID: {record.id}",
            f"Question: {record.question}",
            f"Expected files: {record.relevant_files}",
            f"Expected symbols: {record.relevant_symbols}",
            f"Human notes: {record.notes}",
            "Answer JSON:",
            answer.model_dump_json(),
        ]
    )


def _create_structured_response[T: BaseModel](
    *,
    client: OpenAI,
    model: str,
    prompt: str,
    response_model: type[T],
) -> T:
    parse = cast(Any, client.responses.parse)
    response = parse(
        model=model,
        input=prompt,
        text_format=response_model,
    )
    parsed = cast(T | None, response.output_parsed)
    if parsed is None:
        raise ValueError("model returned no parsed structured output")
    return parsed


def _research_mode_from_question_type(question_type: str) -> ResearchMode:
    mapping = {
        "locate": ResearchMode.LOCATE,
        "flow": ResearchMode.FLOW,
        "change": ResearchMode.CHANGE,
    }
    return mapping.get(question_type, ResearchMode.AUTO)
