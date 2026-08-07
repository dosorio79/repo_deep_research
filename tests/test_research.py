"""Tests for bounded agentic research behavior."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from repo_research.grounding import canonical_change_targets
from repo_research.models import (
    ChangeTarget,
    EvidenceItem,
    ModelUsage,
    ParsedChunk,
    RagMode,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchBudget,
    ResearchRequest,
    ResearchStep,
    RetrievalMode,
    SearchQuery,
    SearchResult,
)
from repo_research.research import (
    BoundedResearchService,
    ResearchAgentResult,
    ResearchAgentRunError,
    ResearchBudgetExceeded,
    ResearchToolContext,
    _model_usage_from_agent_usage,
)


class FakeDatabase:
    """Return fixed search results and capture queries."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.queries: list[SearchQuery] = []

    def search(self, query: SearchQuery) -> list[SearchResult]:
        self.queries.append(query)
        return self._results


class InitialSearchFailingDatabase:
    """Raise before the agent receives seeded evidence."""

    def search(self, query: SearchQuery) -> list[SearchResult]:
        del query
        raise ValueError("initial search failed")


class ScriptedAgent:
    """Run a deterministic script against repository tools."""

    def __init__(self, answer: ResearchAnswer) -> None:
        self._answer = answer

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        assert request.question
        tools.search_repository("configuration settings")
        return ResearchAgentResult(answer=self._answer)


class UnknownEvidenceAgent:
    """Return an answer that cites evidence the tools never returned."""

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        tools.search_repository("configuration settings")
        return ResearchAgentResult(
            answer=ResearchAnswer(
                question=request.question,
                summary="Unsupported answer.",
                evidence=[
                    EvidenceItem(
                        evidence_id="E99",
                        path="invented.py",
                        start_line=1,
                        end_line=1,
                        symbol=None,
                        score=0.0,
                        reason="Not actually available.",
                    )
                ],
                confidence=0.2,
            )
        )


class BudgetExhaustingAgent:
    """Call tools until the configured budget fails."""

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        tools.search_repository("first")
        tools.search_repository("second")
        return ResearchAgentResult(
            answer=ResearchAnswer(
                question=request.question,
                summary="Should not be returned.",
                confidence=0.1,
                insufficient_evidence=True,
            )
        )


class FailingUsageAgent:
    """Fail after a model call while preserving usage telemetry."""

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        tools.search_repository("settings")
        raise ResearchAgentRunError(
            "maximum search calls exceeded",
            usage=ModelUsage(
                provider="openai",
                model="gpt-5-mini",
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
            ),
            error_type="ResearchBudgetExceeded",
        )


class FakeAgentUsage:
    """Minimal PydanticAI run usage shape for telemetry conversion tests."""

    input_tokens = 1_000
    output_tokens = 200
    cache_read_tokens = 100
    details = {"reasoning_tokens": 25}


class FakeEmptyAgentUsage:
    """Minimal empty PydanticAI run usage shape."""

    def has_values(self) -> bool:
        return False


@dataclass
class ProtocolChangeTarget:
    """Protocol-shaped target that bypasses Pydantic model validation."""

    reason: str
    evidence_ids: list[str]


def test_research_service_canonicalizes_agent_evidence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    chunk = _chunk(repository)
    database = FakeDatabase([SearchResult(chunk=chunk, score=0.9)])
    service = BoundedResearchService(
        database=database,
        agent=ScriptedAgent(
            ResearchAnswer(
                question="Which modules change for bounded research?",
                summary="Add a bounded research service.",
                research_steps=[
                    ResearchStep(
                        sequence=1,
                        action="search_repository",
                        rationale="Find the existing settings contract.",
                        evidence_ids=["E1"],
                    )
                ],
                evidence=[
                    EvidenceItem(
                        evidence_id="E1",
                        path="wrong.py",
                        start_line=99,
                        end_line=100,
                        symbol="Wrong",
                        score=0.0,
                        reason="The agent selects the settings evidence.",
                    )
                ],
                change_targets=[
                    ChangeTarget(
                        path="wrong.py",
                        symbol="Wrong",
                        reason="Add M4 settings beside current settings.",
                        evidence_ids=["E1"],
                    )
                ],
                confidence=0.8,
            )
        ),
    )

    run = service.run(
        repository=repository,
        request=ResearchRequest(
            question="Which modules change for bounded research?",
            mode=RagMode.CHANGE,
        ),
    )

    assert run.answer.insufficient_evidence is False
    assert run.answer.evidence[0].path == "src/repo_research/config.py"
    assert run.answer.evidence[0].start_line == 1
    assert run.answer.change_targets[0].path == "src/repo_research/config.py"
    assert run.answer.relevant_files == ["src/repo_research/config.py"]
    assert run.trace.tool_call_count == 1
    assert run.trace.retrieved_chunk_count == 1
    assert run.trace.evidence_ids == ["E1"]
    assert "change impact" in database.queries[0].text
    assert "BoundedResearchService" not in database.queries[0].text


def test_canonical_change_targets_skips_targets_without_valid_evidence() -> None:
    evidence = EvidenceItem(
        evidence_id="E1",
        path="src/repo_research/config.py",
        start_line=1,
        end_line=3,
        symbol="Settings",
        score=0.9,
        reason="Canonical evidence.",
    )

    targets = canonical_change_targets(
        [
            ProtocolChangeTarget(reason="No evidence.", evidence_ids=[]),
            ProtocolChangeTarget(reason="Unknown evidence.", evidence_ids=["E99"]),
            ProtocolChangeTarget(
                reason="Use valid evidence.", evidence_ids=["E99", "E1"]
            ),
        ],
        {"E1": evidence},
    )

    assert len(targets) == 1
    assert targets[0].path == "src/repo_research/config.py"
    assert targets[0].symbol == "Settings"
    assert targets[0].evidence_ids == ["E1"]


def test_research_agent_usage_maps_to_trace_model_usage() -> None:
    usage = _model_usage_from_agent_usage(
        provider="openai",
        model="gpt-5-mini",
        usage=FakeAgentUsage(),
    )

    assert usage is not None
    assert usage.provider == "openai"
    assert usage.model == "gpt-5-mini"
    assert usage.input_tokens == 1_000
    assert usage.output_tokens == 200
    assert usage.total_tokens == 1_200
    assert usage.cached_input_tokens == 100
    assert usage.reasoning_tokens == 25
    assert usage.estimated_cost_usd is not None
    assert usage.pricing_source != "unknown"


def test_research_agent_usage_ignores_empty_run_usage() -> None:
    usage = _model_usage_from_agent_usage(
        provider="openai",
        model="gpt-5-mini",
        usage=FakeEmptyAgentUsage(),
    )

    assert usage is None


def test_research_service_preserves_model_usage_on_agent_error(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = BoundedResearchService(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        agent=FailingUsageAgent(),
    )

    run = service.run(
        repository=repository,
        request=ResearchRequest(question="Which modules change?"),
    )

    assert run.answer.insufficient_evidence is False
    assert run.answer.change_targets
    assert run.trace.error_type == "ResearchBudgetExceeded"
    assert run.trace.model_usage[0].input_tokens == 100
    assert run.trace.model_usage[0].output_tokens == 25
    assert run.trace.total_estimated_cost_usd is None


def test_research_service_returns_fallback_when_initial_search_fails(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    service = BoundedResearchService(
        database=InitialSearchFailingDatabase(),
        agent=ScriptedAgent(
            ResearchAnswer(
                question="Which modules change?",
                summary="Should not run.",
                confidence=0.1,
            )
        ),
    )

    run = service.run(
        repository=repository,
        request=ResearchRequest(question="Which modules change?"),
    )

    assert run.answer.insufficient_evidence is True
    assert run.answer.evidence == []
    assert run.trace.error_type == "ValueError"
    assert run.trace.error_message == "initial search failed"
    assert run.trace.latency_ms_model is not None


def test_research_service_rejects_unknown_agent_evidence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = BoundedResearchService(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        agent=UnknownEvidenceAgent(),
    )

    run = service.run(
        repository=repository,
        request=ResearchRequest(question="Which modules change?"),
    )

    assert run.answer.insufficient_evidence is True
    assert run.answer.evidence[0].path == "src/repo_research/config.py"
    assert "unknown evidence IDs" in run.answer.unresolved_questions[0]


def test_research_service_returns_bounded_change_plan_on_search_budget(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    service = BoundedResearchService(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        agent=BudgetExhaustingAgent(),
    )

    run = service.run(
        repository=repository,
        request=ResearchRequest(
            question="Which modules change?",
            budget=ResearchBudget(
                max_searches=1,
                max_file_reads=1,
                max_total_tool_calls=2,
            ),
        ),
    )

    assert run.answer.insufficient_evidence is False
    assert run.answer.summary.startswith("Bounded change-impact plan")
    assert run.answer.evidence[0].path == "src/repo_research/config.py"
    assert run.answer.change_targets[0].path == "src/repo_research/config.py"
    assert run.answer.change_targets[0].evidence_ids == ["E1"]
    assert (
        run.answer.research_steps[1].action == "Stopped at configured research budget."
    )
    assert any("tests" in step.lower() for step in run.answer.implementation_flow)
    assert run.answer.confidence == 0.35
    assert run.trace.error_type == "ResearchBudgetExceeded"
    assert run.trace.error_message is not None
    assert "maximum search calls exceeded" in run.trace.error_message
    assert run.trace.tool_call_count == 1


def test_research_tools_block_file_reads_outside_root(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    tools = ResearchToolContext(
        database=FakeDatabase([]),
        repository=repository,
        root_path=tmp_path,
        request=ResearchRequest(question="Read a file"),
    )

    with pytest.raises(ValueError, match="cannot escape"):
        tools.read_file("../outside.py")


def test_research_tools_read_file_adds_citable_evidence(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "line1\nline2\nline3\n",
        encoding="utf-8",
    )
    repository = _repository(tmp_path)
    tools = ResearchToolContext(
        database=FakeDatabase([]),
        repository=repository,
        root_path=tmp_path,
        request=ResearchRequest(question="Read a file"),
    )

    evidence = tools.read_file("module.py", start_line=2, end_line=3)

    assert evidence.evidence_id == "E1"
    assert evidence.path == "module.py"
    assert evidence.start_line == 2
    assert evidence.end_line == 3
    assert evidence.content == "line2\nline3"
    assert tools.file_read_calls == 1
    assert tools.total_tool_calls == 1


def test_research_tools_enforce_total_tool_budget(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    tools = ResearchToolContext(
        database=FakeDatabase([SearchResult(chunk=_chunk(repository), score=0.9)]),
        repository=repository,
        root_path=tmp_path,
        request=ResearchRequest(
            question="Find settings",
            budget=ResearchBudget(
                max_searches=1,
                max_file_reads=1,
                max_total_tool_calls=1,
            ),
        ),
    )

    tools.search_repository("settings")
    with pytest.raises(ResearchBudgetExceeded, match="total"):
        tools.read_chunk("E1")


def test_research_tools_find_symbol_filters_results(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    database = FakeDatabase(
        [
            SearchResult(chunk=_chunk(repository, symbol="Settings"), score=0.9),
            SearchResult(chunk=_chunk(repository, symbol="Other"), score=0.8),
        ]
    )
    tools = ResearchToolContext(
        database=database,
        repository=repository,
        root_path=tmp_path,
        request=ResearchRequest(question="Find Settings"),
    )

    evidence = tools.find_symbol("Settings")

    assert [item.symbol for item in evidence] == ["Settings"]
    assert database.queries[0].text == "Settings"
    assert database.queries[0].mode is RetrievalMode.DENSE


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
    symbol: str = "Settings",
) -> ParsedChunk:
    return ParsedChunk(
        chunk_id=f"{path}:{symbol}",
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        path=path,
        language="python",
        chunk_type="class",
        symbol=symbol,
        start_line=1,
        end_line=3,
        content="class Settings:\n    pass\n",
        content_hash=f"hash-{path}-{symbol}",
    )
