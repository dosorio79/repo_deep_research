"""Grounded direct-RAG answer generation and evaluation services."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from repo_research.config import load_dotenv_environment
from repo_research.evaluation import load_records
from repo_research.models import (
    AnswerEvaluationResult,
    ChangeTarget,
    EvaluationRecord,
    EvidenceItem,
    RagAnswer,
    RagMode,
    RagRequest,
    RepositoryIdentity,
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
        request: RagRequest,
        evidence_context: str,
    ) -> RagAnswerDraft:
        """Return a model draft that cites opaque evidence IDs only."""


class AnswerJudge(Protocol):
    """Model adapter for judging a grounded answer against a record."""

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: RagAnswer,
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


class RagAnswerDraft(BaseModel):
    """Structured model output before canonical citation validation."""

    summary: str = Field(min_length=1)
    implementation_flow: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    change_targets: list[ChangeTargetDraft] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class DirectRagService:
    """Answer repository questions using one retrieval pass and grounded citations."""

    def __init__(
        self,
        *,
        database: RepositorySearcher,
        generator: AnswerGenerator,
    ) -> None:
        self._database = database
        self._generator = generator

    def answer(
        self,
        *,
        repository: RepositoryIdentity,
        request: RagRequest,
    ) -> RagAnswer:
        """Return a direct-RAG answer with citations validated against retrieval."""
        request = request.model_copy(update={"mode": infer_rag_mode(request)})
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
            return insufficient_evidence_rag_answer(
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
            return insufficient_evidence_rag_answer(
                request=request,
                reason=f"Answer generation failed validation: {error}",
                closest_evidence=evidence_by_id.values(),
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
        load_dotenv_environment()
        self._client = OpenAI()

    def generate_answer(
        self,
        *,
        request: RagRequest,
        evidence_context: str,
    ) -> RagAnswerDraft:
        """Generate a structured answer draft with the configured answer model."""
        prompt = _answer_prompt(request=request, evidence_context=evidence_context)
        return _create_structured_response(
            client=self._client,
            model=self._answer_model,
            prompt=prompt,
            response_model=RagAnswerDraft,
        )

    def judge_answer(
        self,
        *,
        record: EvaluationRecord,
        answer: RagAnswer,
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
    service: DirectRagService,
    judge: AnswerJudge,
    repository: RepositoryIdentity,
    records: list[EvaluationRecord],
    retrieval_mode: RetrievalMode,
    limit: int,
) -> list[AnswerEvaluationResult]:
    """Run direct RAG and judge evaluation for versioned records."""
    results: list[AnswerEvaluationResult] = []
    for record in records:
        answer = service.answer(
            repository=repository,
            request=RagRequest(
                question=record.question,
                mode=_rag_mode_from_question_type(record.question_type),
                retrieval_mode=retrieval_mode,
                limit=limit,
            ),
        )
        results.append(judge.judge_answer(record=record, answer=answer))
    return results


def evaluate_answers_from_dataset(
    *,
    service: DirectRagService,
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


def insufficient_evidence_rag_answer(
    *,
    request: RagRequest,
    reason: str,
    closest_evidence: Iterable[EvidenceItem] = (),
) -> RagAnswer:
    """Return a deterministic answer when evidence or validation is insufficient."""
    evidence = _closest_evidence_items(closest_evidence)
    return RagAnswer(
        question=request.question,
        mode=request.mode,
        summary="Insufficient repository evidence to answer the question.",
        implementation_flow=[],
        evidence=evidence,
        relevant_files=sorted({item.path for item in evidence}),
        relevant_symbols=sorted({item.symbol for item in evidence if item.symbol}),
        change_targets=[],
        risks=["The answer is intentionally withheld because grounding failed."],
        confidence=0.0,
        unresolved_questions=[reason],
        insufficient_evidence=True,
    )


def infer_rag_mode(request: RagRequest) -> RagMode:
    """Resolve auto mode from common repository-question wording."""
    if request.mode is not RagMode.AUTO:
        return request.mode
    question = request.question.strip().lower()
    if question.startswith(("where is", "where are", "where does")):
        return RagMode.LOCATE
    tokens = set(re.findall(r"[a-z0-9_]+", question))
    change_terms = {
        "add",
        "adapt",
        "change",
        "changes",
        "modify",
        "support",
        "update",
    }
    if question.startswith(
        ("what change", "what changes", "which files", "where to modify")
    ) or tokens.intersection(change_terms):
        return RagMode.CHANGE
    if question.startswith(("how does", "how do", "how to")) or "flow" in tokens:
        return RagMode.FLOW
    return RagMode.AUTO


def _build_validated_answer(
    *,
    request: RagRequest,
    draft: RagAnswerDraft,
    evidence_by_id: dict[str, EvidenceItem],
) -> RagAnswer:
    referenced_ids = [reference.evidence_id for reference in draft.evidence]
    if not referenced_ids and not draft.insufficient_evidence:
        return insufficient_evidence_rag_answer(
            request=request,
            reason="Model returned an answer without citing retrieved evidence.",
            closest_evidence=evidence_by_id.values(),
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
        return insufficient_evidence_rag_answer(
            request=request,
            reason=f"Model cited unknown evidence IDs: {sorted(set(unknown_ids))}",
            closest_evidence=evidence_by_id.values(),
        )

    evidence = [
        evidence_by_id[reference.evidence_id].model_copy(
            update={"reason": reference.reason}
        )
        for reference in draft.evidence
    ]
    relevant_files = sorted({item.path for item in evidence})
    relevant_symbols = sorted({item.symbol for item in evidence if item.symbol})
    change_targets = (
        _canonical_change_targets(draft.change_targets, evidence_by_id)
        if request.mode is RagMode.CHANGE
        else []
    )
    return RagAnswer(
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
        unresolved_questions=_filtered_unresolved_questions(draft.unresolved_questions),
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


def _closest_evidence_items(
    closest_evidence: Iterable[EvidenceItem],
) -> list[EvidenceItem]:
    return [
        item.model_copy(update={"reason": "Closest retrieved repository evidence."})
        for item in closest_evidence
    ]


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


def _answer_prompt(*, request: RagRequest, evidence_context: str) -> str:
    return "\n\n".join(
        [
            "You answer questions about a Python repository using only the provided "
            "evidence. Cite evidence by evidence_id only. Do not emit source paths "
            "or line numbers; the application maps evidence IDs to canonical "
            "citations. If the evidence is insufficient, set insufficient_evidence "
            "to true and explain what is missing.",
            "Use change_targets only when RAG mode is change. For locate and flow "
            "modes, leave change_targets empty.",
            "Do not ask whether the user wants paths, line numbers, or citations; "
            "the application returns canonical evidence separately.",
            "For locate questions, prefer evidence containing concrete symbols, "
            "classes, functions, validators, or assignments over module docstrings "
            "or import-only chunks.",
            f"RAG mode: {request.mode.value}",
            f"Question: {request.question}",
            "Evidence:",
            evidence_context,
        ]
    )


def _filtered_unresolved_questions(questions: list[str]) -> list[str]:
    filtered: list[str] = []
    for question in questions:
        lowered = question.lower()
        asks_preference = "do you want" in lowered or "would you like" in lowered
        asks_for_returned_metadata = any(
            fragment in lowered
            for fragment in (
                "path",
                "line",
                "citation",
                "file reference",
            )
        )
        if asks_preference and asks_for_returned_metadata:
            continue
        filtered.append(question)
    return filtered


def _judge_prompt(*, record: EvaluationRecord, answer: RagAnswer) -> str:
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


def _rag_mode_from_question_type(question_type: str) -> RagMode:
    mapping = {
        "locate": RagMode.LOCATE,
        "flow": RagMode.FLOW,
        "change": RagMode.CHANGE,
    }
    return mapping.get(question_type, RagMode.AUTO)
