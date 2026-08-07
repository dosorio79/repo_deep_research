"""Bounded agentic research service and PydanticAI adapter."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import RunUsage

from repo_research.config import load_dotenv_environment
from repo_research.grounding import canonical_change_targets
from repo_research.models import (
    ChangeTarget,
    EvidenceItem,
    ModelUsage,
    RagMode,
    RagRequest,
    RagRunTrace,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchRequest,
    ResearchRunResult,
    ResearchStep,
    SearchQuery,
    SearchResult,
)
from repo_research.pricing import estimate_openai_price
from repo_research.protocols import RepositorySearcher
from repo_research.rag import infer_rag_mode
from repo_research.telemetry import elapsed_ms, total_estimated_cost, usage_int


class ResearchBudgetExceeded(ValueError):
    """Raised when a research tool call would exceed configured bounds."""


class ResearchAgentRunError(ValueError):
    """Raised when the live agent fails after collecting model usage."""

    def __init__(
        self,
        message: str,
        *,
        usage: ModelUsage | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.error_type = error_type or type(self).__name__


class ToolEvidence(BaseModel):
    """Repository evidence returned by an agent tool, including inspectable content."""

    evidence_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None
    score: float
    reason: str = Field(min_length=1)
    content: str = Field(min_length=1)
    chunk_id: str | None = None

    @property
    def evidence_item(self) -> EvidenceItem:
        """Return the canonical citation shape exposed in final answers."""
        return EvidenceItem(
            evidence_id=self.evidence_id,
            path=self.path,
            start_line=self.start_line,
            end_line=self.end_line,
            symbol=self.symbol,
            score=self.score,
            reason=self.reason,
        )


@dataclass(frozen=True)
class ResearchAgentResult:
    """Agent output plus optional model usage telemetry."""

    answer: ResearchAnswer
    usage: ModelUsage | None = None


class ResearchAgentRunner(Protocol):
    """Fakeable agent boundary used by the service."""

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        """Run bounded research with the provided repository tools."""


class ResearchToolContext:
    """Stateful, bounded repository tools exposed to the research agent."""

    def __init__(
        self,
        *,
        database: RepositorySearcher,
        repository: RepositoryIdentity,
        root_path: Path,
        request: ResearchRequest,
        seed_evidence: Iterable[SearchResult] = (),
    ) -> None:
        self._database = database
        self._repository = repository
        self._root_path = root_path.resolve()
        self._request = request
        self._next_evidence_index = 1
        self._evidence_by_id: dict[str, ToolEvidence] = {}
        self._evidence_by_chunk_id: dict[str, ToolEvidence] = {}
        self.search_calls = 0
        self.file_read_calls = 0
        self.total_tool_calls = 0
        for result in seed_evidence:
            self._record_search_result(result, reason="Initial repository evidence.")

    @property
    def evidence(self) -> list[ToolEvidence]:
        """Return all evidence made available to the agent."""
        return list(self._evidence_by_id.values())

    @property
    def evidence_by_id(self) -> dict[str, ToolEvidence]:
        """Return canonical evidence keyed by evidence ID."""
        return dict(self._evidence_by_id)

    def search_repository(
        self, query: str, limit: int | None = None
    ) -> list[ToolEvidence]:
        """Search indexed repository chunks for the current commit."""
        self._consume_tool_call(kind="search")
        bounded_limit = self._bounded_limit(limit)
        results = self._database.search(
            SearchQuery(
                text=query,
                repository_id=self._repository.repository_id,
                commit_hash=self._repository.commit_hash,
                limit=bounded_limit,
                mode=self._request.retrieval_mode,
            )
        )
        return [
            self._record_search_result(result, reason="Retrieved repository evidence.")
            for result in results
        ]

    def read_chunk(self, evidence_or_chunk_id: str) -> ToolEvidence | None:
        """Return a previously retrieved chunk by evidence ID or chunk ID."""
        self._consume_tool_call(kind="total")
        evidence = self._evidence_by_id.get(evidence_or_chunk_id)
        if evidence is not None:
            return evidence
        return self._evidence_by_chunk_id.get(evidence_or_chunk_id)

    def read_file(
        self,
        relative_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolEvidence:
        """Read a repository file slice without allowing root escape."""
        self._consume_tool_call(kind="file_read")
        target = self._safe_repository_path(relative_path)
        lines = target.read_text(encoding="utf-8").splitlines()
        if not lines:
            lines = [""]
        start = max(1, start_line or 1)
        end = min(len(lines), end_line or len(lines))
        if end < start:
            raise ValueError("end_line must be greater than or equal to start_line")
        content = "\n".join(lines[start - 1 : end]) or " "
        evidence = ToolEvidence(
            evidence_id=self._next_evidence_id(),
            path=target.relative_to(self._root_path).as_posix(),
            start_line=start,
            end_line=end,
            symbol=None,
            score=1.0,
            reason="Read repository file evidence.",
            content=content,
            chunk_id=None,
        )
        self._evidence_by_id[evidence.evidence_id] = evidence
        return evidence

    def find_symbol(self, symbol: str) -> list[ToolEvidence]:
        """Find symbol matches within the bounded semantic search result set."""
        self._consume_tool_call(kind="search")
        results = self._database.search(
            SearchQuery(
                text=symbol,
                repository_id=self._repository.repository_id,
                commit_hash=self._repository.commit_hash,
                limit=self._request.retrieval_limit,
                mode=self._request.retrieval_mode,
            )
        )
        matched = [
            result
            for result in results
            if result.chunk.symbol == symbol
            or (result.chunk.symbol or "").endswith(f".{symbol}")
        ]
        return [
            self._record_search_result(result, reason="Matched repository symbol.")
            for result in matched
        ]

    def _consume_tool_call(self, *, kind: str) -> None:
        if self.total_tool_calls >= self._request.budget.max_total_tool_calls:
            raise ResearchBudgetExceeded("maximum total tool calls exceeded")
        if kind == "search":
            if self.search_calls >= self._request.budget.max_searches:
                raise ResearchBudgetExceeded("maximum search calls exceeded")
            self.search_calls += 1
        elif kind == "file_read":
            if self.file_read_calls >= self._request.budget.max_file_reads:
                raise ResearchBudgetExceeded("maximum file reads exceeded")
            self.file_read_calls += 1
        self.total_tool_calls += 1

    def _bounded_limit(self, limit: int | None) -> int:
        if limit is None:
            return self._request.retrieval_limit
        return min(max(1, limit), self._request.retrieval_limit)

    def _record_search_result(
        self, result: SearchResult, *, reason: str
    ) -> ToolEvidence:
        existing = self._evidence_by_chunk_id.get(result.chunk.chunk_id)
        if existing is not None:
            return existing
        evidence = ToolEvidence(
            evidence_id=self._next_evidence_id(),
            path=result.chunk.path,
            start_line=result.chunk.start_line,
            end_line=result.chunk.end_line,
            symbol=result.chunk.symbol,
            score=result.score,
            reason=reason,
            content=result.chunk.content,
            chunk_id=result.chunk.chunk_id,
        )
        self._evidence_by_id[evidence.evidence_id] = evidence
        self._evidence_by_chunk_id[result.chunk.chunk_id] = evidence
        return evidence

    def _next_evidence_id(self) -> str:
        evidence_id = f"E{self._next_evidence_index}"
        self._next_evidence_index += 1
        return evidence_id

    def _safe_repository_path(self, relative_path: str) -> Path:
        target = (self._root_path / relative_path).resolve()
        if target != self._root_path and self._root_path not in target.parents:
            raise ValueError("repository file read cannot escape the repository root")
        if not target.is_file():
            raise ValueError(f"repository file does not exist: {relative_path}")
        return target


class BoundedResearchService:
    """Run one bounded agentic research request over repository tools."""

    def __init__(
        self,
        *,
        database: RepositorySearcher,
        agent: ResearchAgentRunner,
    ) -> None:
        self._database = database
        self._agent = agent

    def run(
        self,
        *,
        repository: RepositoryIdentity,
        request: ResearchRequest,
    ) -> ResearchRunResult:
        """Return a grounded research answer plus application-owned trace."""
        started_at = datetime.now(UTC)
        total_start = time.perf_counter()
        request = request.model_copy(
            update={
                "mode": _infer_research_mode(request),
                "repository_path": request.repository_path,
                "session_id": request.session_id or uuid4().hex,
            }
        )
        root_path = (request.repository_path or repository.root_path).resolve()
        tools: ResearchToolContext | None = None
        model_usage: list[ModelUsage] = []
        latency_ms_model: int | None = None
        error_type: str | None = None
        error_message: str | None = None
        model_start = time.perf_counter()
        try:
            tools = ResearchToolContext(
                database=self._database,
                repository=repository,
                root_path=root_path,
                request=request,
                seed_evidence=self._initial_search(
                    repository=repository, request=request
                ),
            )
            model_start = time.perf_counter()
            agent_result = self._agent.run_research(request=request, tools=tools)
            latency_ms_model = elapsed_ms(model_start)
            if agent_result.usage is not None:
                model_usage.append(agent_result.usage)
            answer = _canonical_research_answer(
                request=request,
                answer=agent_result.answer,
                available_evidence=tools.evidence_by_id,
            )
        except ValueError as error:
            if latency_ms_model is None:
                latency_ms_model = elapsed_ms(model_start)
            if tools is None:
                tools = ResearchToolContext(
                    database=self._database,
                    repository=repository,
                    root_path=root_path,
                    request=request,
                )
            usage = getattr(error, "usage", None)
            if isinstance(usage, ModelUsage):
                model_usage.append(usage)
            error_type = getattr(error, "error_type", type(error).__name__)
            error_message = str(error)
            answer = _bounded_change_plan_answer(
                request=request,
                reason=str(error),
                error_type=error_type,
                closest_evidence=tools.evidence,
                tool_call_count=tools.total_tool_calls,
            ) or insufficient_evidence_research_answer(
                request=request,
                reason=str(error),
                closest_evidence=tools.evidence,
            )
        completed_at = datetime.now(UTC)
        return ResearchRunResult(
            answer=answer,
            trace=_build_research_trace(
                request_id=uuid4().hex,
                started_at=started_at,
                completed_at=completed_at,
                repository=repository,
                request=request,
                evidence=tools.evidence,
                answer=answer,
                latency_ms_total=elapsed_ms(total_start),
                latency_ms_model=latency_ms_model,
                model_usage=model_usage,
                error_type=error_type,
                error_message=error_message,
                tool_call_count=tools.total_tool_calls,
            ),
        )

    def _initial_search(
        self,
        *,
        repository: RepositoryIdentity,
        request: ResearchRequest,
    ) -> list[SearchResult]:
        """Seed the agent with evidence without spending its follow-up budget."""
        return self._database.search(
            SearchQuery(
                text=_initial_search_text(request),
                repository_id=repository.repository_id,
                commit_hash=repository.commit_hash,
                limit=request.retrieval_limit,
                mode=request.retrieval_mode,
            )
        )


@dataclass(frozen=True)
class PydanticResearchDeps:
    """Dependencies passed into the PydanticAI research agent."""

    tools: ResearchToolContext


class PydanticAIResearchAgent:
    """Live PydanticAI adapter for bounded repository research."""

    def __init__(self, *, model: str) -> None:
        load_dotenv_environment()
        provider, model_name = _split_provider_model(model)
        self._provider = provider
        self._model_name = model_name
        self._model = model if ":" in model else f"{provider}:{model_name}"
        self._agent: Agent[PydanticResearchDeps, ResearchAnswer] = Agent(
            self._model,
            deps_type=PydanticResearchDeps,
            output_type=ResearchAnswer,
            system_prompt=_research_system_prompt(),
        )
        self._register_tools()

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        """Run the live PydanticAI agent and return structured output."""
        run_usage = RunUsage()
        try:
            result = self._agent.run_sync(
                _research_user_prompt(request=request, evidence=tools.evidence),
                deps=PydanticResearchDeps(tools=tools),
                usage=run_usage,
            )
        except ValueError as error:
            raise ResearchAgentRunError(
                str(error),
                usage=_model_usage_from_agent_usage(
                    provider=self._provider,
                    model=self._model_name,
                    usage=run_usage,
                ),
                error_type=type(error).__name__,
            ) from error
        usage = result.usage
        if usage is None or not usage.has_values():
            usage = run_usage
        return ResearchAgentResult(
            answer=result.output,
            usage=_model_usage_from_agent_usage(
                provider=self._provider,
                model=self._model_name,
                usage=usage,
            ),
        )

    def _register_tools(self) -> None:
        @self._agent.tool
        def search_repository(
            ctx: RunContext[PydanticResearchDeps],
            query: str,
            limit: int | None = None,
        ) -> list[ToolEvidence]:
            """Search indexed repository evidence for the current commit."""
            return ctx.deps.tools.search_repository(query=query, limit=limit)

        @self._agent.tool
        def read_chunk(
            ctx: RunContext[PydanticResearchDeps], evidence_or_chunk_id: str
        ) -> ToolEvidence | None:
            """Read a previously retrieved chunk by evidence ID or chunk ID."""
            return ctx.deps.tools.read_chunk(evidence_or_chunk_id)

        @self._agent.tool
        def read_file(
            ctx: RunContext[PydanticResearchDeps],
            relative_path: str,
            start_line: int | None = None,
            end_line: int | None = None,
        ) -> ToolEvidence:
            """Read a repository file slice by relative path."""
            return ctx.deps.tools.read_file(
                relative_path=relative_path,
                start_line=start_line,
                end_line=end_line,
            )

        @self._agent.tool
        def find_symbol(
            ctx: RunContext[PydanticResearchDeps], symbol: str
        ) -> list[ToolEvidence]:
            """Find indexed repository evidence for a symbol."""
            return ctx.deps.tools.find_symbol(symbol)


def insufficient_evidence_research_answer(
    *,
    request: ResearchRequest,
    reason: str,
    closest_evidence: Iterable[ToolEvidence] = (),
) -> ResearchAnswer:
    """Return a deterministic research answer when grounding fails."""
    evidence = [
        item.evidence_item.model_copy(
            update={"reason": "Closest available repository evidence."}
        )
        for item in closest_evidence
    ]
    return ResearchAnswer(
        question=request.question,
        mode=request.mode,
        summary="Insufficient repository evidence to produce an agentic change plan.",
        research_steps=[],
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


def _bounded_change_plan_answer(
    *,
    request: ResearchRequest,
    reason: str,
    error_type: str | None,
    closest_evidence: Iterable[ToolEvidence],
    tool_call_count: int,
) -> ResearchAnswer | None:
    """Return a useful low-confidence change plan from evidence collected so far."""
    evidence = [
        item.evidence_item.model_copy(
            update={"reason": "Collected before the bounded agent stopped."}
        )
        for item in closest_evidence
    ]
    if (
        request.mode is not RagMode.CHANGE
        or error_type != "ResearchBudgetExceeded"
        or not evidence
    ):
        return None

    evidence_by_target = _change_target_evidence(evidence)
    evidence_ids = [item.evidence_id for item in evidence]
    return ResearchAnswer(
        question=request.question,
        mode=request.mode,
        summary=(
            "Bounded change-impact plan from the repository evidence collected before "
            "the agent reached its tool budget."
        ),
        research_steps=[
            ResearchStep(
                sequence=1,
                action="Reviewed collected repository evidence.",
                rationale=(
                    "Use the evidence already retrieved or read by the bounded agent "
                    "instead of inventing unsupported files."
                ),
                evidence_ids=evidence_ids,
            ),
            ResearchStep(
                sequence=2,
                action="Stopped at configured research budget.",
                rationale=(
                    "Return a conservative partial plan with explicit uncertainty "
                    "rather than discarding useful evidence."
                ),
                evidence_ids=evidence_ids,
            ),
        ],
        implementation_flow=[
            (
                "Start with the cited files and symbols because they are the "
                "concrete repository surfaces retrieved for the requested change."
            ),
            (
                "Inspect adjacent callers, configuration, and tests before editing; "
                "the bounded run may not have followed every reference."
            ),
            (
                "Apply the change in the smallest vertical slice and validate it "
                "with focused tests around the cited modules."
            ),
        ],
        evidence=evidence,
        relevant_files=sorted({item.path for item in evidence}),
        relevant_symbols=sorted({item.symbol for item in evidence if item.symbol}),
        change_targets=[
            ChangeTarget(
                path=path,
                symbol=symbol,
                reason=(
                    "Likely change surface because the bounded agent collected "
                    "repository evidence here for the requested adaptation."
                ),
                evidence_ids=target_evidence_ids,
            )
            for (path, symbol), target_evidence_ids in evidence_by_target.items()
        ],
        risks=[
            (
                f"The agent stopped after {tool_call_count} tool calls, so this "
                "plan may miss secondary callers or tests."
            ),
            (
                "Validate each target against the full repository before "
                "implementing changes."
            ),
            (
                "Run the relevant unit or contract tests for every cited module "
                "after editing."
            ),
        ],
        confidence=0.35,
        unresolved_questions=[
            reason,
            "A larger budget or follow-up run may identify additional change targets.",
        ],
        insufficient_evidence=False,
    )


def _change_target_evidence(
    evidence: list[EvidenceItem],
) -> dict[tuple[str, str | None], list[str]]:
    target_evidence: dict[tuple[str, str | None], list[str]] = {}
    for item in evidence:
        key = (item.path, item.symbol)
        target_evidence.setdefault(key, []).append(item.evidence_id)
    return target_evidence


def _canonical_research_answer(
    *,
    request: ResearchRequest,
    answer: ResearchAnswer,
    available_evidence: dict[str, ToolEvidence],
) -> ResearchAnswer:
    referenced_ids = {item.evidence_id for item in answer.evidence}
    referenced_ids.update(
        evidence_id
        for step in answer.research_steps
        for evidence_id in step.evidence_ids
    )
    referenced_ids.update(
        evidence_id
        for target in answer.change_targets
        for evidence_id in target.evidence_ids
    )
    if not referenced_ids and not answer.insufficient_evidence:
        return insufficient_evidence_research_answer(
            request=request,
            reason="Agent returned an answer without citing tool evidence.",
            closest_evidence=available_evidence.values(),
        )
    unknown_ids = sorted(referenced_ids - set(available_evidence))
    if unknown_ids:
        return insufficient_evidence_research_answer(
            request=request,
            reason=f"Agent cited unknown evidence IDs: {unknown_ids}",
            closest_evidence=available_evidence.values(),
        )
    evidence = [
        available_evidence[item.evidence_id].evidence_item.model_copy(
            update={"reason": item.reason}
        )
        for item in answer.evidence
    ]
    evidence_by_id = {item.evidence_id: item for item in evidence}
    relevant_files = sorted({item.path for item in evidence})
    relevant_symbols = sorted({item.symbol for item in evidence if item.symbol})
    return ResearchAnswer(
        question=request.question,
        mode=request.mode,
        summary=answer.summary,
        research_steps=answer.research_steps,
        implementation_flow=answer.implementation_flow,
        evidence=evidence,
        relevant_files=relevant_files,
        relevant_symbols=relevant_symbols,
        change_targets=canonical_change_targets(
            answer.change_targets,
            evidence_by_id,
        ),
        risks=answer.risks,
        confidence=answer.confidence,
        unresolved_questions=answer.unresolved_questions,
        insufficient_evidence=answer.insufficient_evidence,
    )


def _build_research_trace(
    *,
    request_id: str,
    started_at: datetime,
    completed_at: datetime,
    repository: RepositoryIdentity,
    request: ResearchRequest,
    evidence: list[ToolEvidence],
    answer: ResearchAnswer,
    latency_ms_total: int,
    latency_ms_model: int | None,
    model_usage: list[ModelUsage],
    error_type: str | None,
    error_message: str | None,
    tool_call_count: int,
) -> RagRunTrace:
    unique_files = {item.path for item in evidence}
    return RagRunTrace(
        request_id=request_id,
        session_id=request.session_id or uuid4().hex,
        started_at=started_at,
        completed_at=completed_at,
        repository_id=repository.repository_id,
        repository_name=repository.name,
        branch=repository.branch,
        commit_hash=repository.commit_hash,
        question_mode=request.mode,
        retrieval_mode=request.retrieval_mode,
        retrieval_limit=request.retrieval_limit,
        retrieved_chunk_count=sum(1 for item in evidence if item.chunk_id is not None),
        unique_file_count=len(unique_files),
        evidence_ids=[item.evidence_id for item in answer.evidence],
        latency_ms_total=latency_ms_total,
        latency_ms_retrieval=max(0, latency_ms_total - (latency_ms_model or 0)),
        latency_ms_model=latency_ms_model,
        model_usage=model_usage,
        total_estimated_cost_usd=total_estimated_cost(model_usage),
        insufficient_evidence=answer.insufficient_evidence,
        error_type=error_type,
        error_message=error_message,
        tool_call_count=tool_call_count,
    )


def _model_usage_from_agent_usage(
    *,
    provider: str,
    model: str,
    usage: object | None,
) -> ModelUsage | None:
    if usage is None:
        return None
    has_values = getattr(usage, "has_values", None)
    if callable(has_values) and not has_values():
        return None
    input_tokens = usage_int(usage, "input_tokens")
    output_tokens = usage_int(usage, "output_tokens")
    total_tokens = usage_int(usage, "total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    cached_input_tokens = usage_int(usage, "cache_read_tokens")
    reasoning_tokens = _usage_detail_int(usage, "reasoning_tokens")
    estimated_cost = None
    pricing_source = "unknown"
    pricing_version = "unknown"
    if provider == "openai" and input_tokens is not None and output_tokens is not None:
        try:
            estimate = estimate_openai_price(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens or 0,
            )
        except ValueError:
            estimate = None
        if estimate is not None:
            estimated_cost = estimate.total_cost_usd
            pricing_source = estimate.pricing_source
            pricing_version = estimate.pricing_version
    return ModelUsage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        estimated_cost_usd=estimated_cost,
        pricing_source=pricing_source,
        pricing_version=pricing_version,
    )


def _split_provider_model(model: str) -> tuple[str, str]:
    if ":" not in model:
        return "openai", model
    provider, model_name = model.split(":", 1)
    return provider, model_name


def _usage_detail_int(usage: object, field_name: str) -> int | None:
    details = getattr(usage, "details", None)
    if not isinstance(details, dict):
        return None
    value = details.get(field_name)
    return value if isinstance(value, int) else None


def _infer_research_mode(request: ResearchRequest) -> RagMode:
    if request.mode is not RagMode.AUTO:
        return request.mode
    inferred = infer_rag_mode(
        RagRequest(
            question=request.question,
            mode=request.mode,
            retrieval_mode=request.retrieval_mode,
            limit=request.retrieval_limit,
        )
    )
    return RagMode.CHANGE if inferred is RagMode.AUTO else inferred


def _initial_search_text(request: ResearchRequest) -> str:
    """Bias first-pass retrieval toward implementation surfaces for change plans."""
    if request.mode is not RagMode.CHANGE:
        return request.question
    return " ".join(
        [
            request.question,
            "change impact",
            "implementation",
            "entry point",
            "call flow",
            "service",
            "configuration",
            "data model",
            "API route",
            "CLI command",
            "persistence",
            "tests",
            "validation",
            "risk",
        ]
    )


def _research_system_prompt() -> str:
    return (
        "You are a bounded repository research agent. Use only the provided tools "
        "to gather evidence. Do not invent paths, symbols, line ranges, files, or "
        "tests. Return structured ResearchAnswer output. Cite evidence by the "
        "evidence_id values returned by tools. You start with initial evidence "
        "already available in the prompt; inspect it before spending follow-up "
        "search calls. Prefer change-impact analysis with risks and unresolved "
        "questions when the mode is change."
    )


def _research_user_prompt(
    *,
    request: ResearchRequest,
    evidence: list[ToolEvidence],
) -> str:
    evidence_lines = [
        "\n".join(
            [
                f"[{item.evidence_id}] {item.path}:{item.start_line}-{item.end_line}",
                f"symbol: {item.symbol or 'None'}",
                f"score: {item.score}",
                "content:",
                item.content,
            ]
        )
        for item in evidence
    ]
    return "\n".join(
        [
            f"Mode: {request.mode.value}",
            f"Retrieval mode: {request.retrieval_mode.value}",
            f"Retrieval limit: {request.retrieval_limit}",
            (
                "Tool budget: "
                f"searches={request.budget.max_searches}, "
                f"file_reads={request.budget.max_file_reads}, "
                f"total_calls={request.budget.max_total_tool_calls}"
            ),
            f"Question: {request.question}",
            "Initial evidence:",
            "\n\n".join(evidence_lines) if evidence_lines else "None",
        ]
    )
