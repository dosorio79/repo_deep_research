"""Offline MVP checks for agentic change-plan usefulness."""

from pathlib import Path

from repo_research.evaluation import load_records
from repo_research.models import (
    ParsedChunk,
    RagMode,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchBudget,
    ResearchRequest,
    SearchQuery,
    SearchResult,
)
from repo_research.research import (
    BoundedResearchService,
    ResearchAgentResult,
    ResearchToolContext,
)


class FixedDatabase:
    """Return deterministic evidence for MVP change-plan checks."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    def search(self, query: SearchQuery) -> list[SearchResult]:
        return self._results

    def get_chunks(
        self, repository_id: str, commit_hash: str, chunk_ids: list[str]
    ) -> list[ParsedChunk]:
        del repository_id, commit_hash, chunk_ids
        return []


class BudgetLimitedAgent:
    """Spend the single search budget so the service must return a partial plan."""

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: ResearchToolContext,
    ) -> ResearchAgentResult:
        tools.search_repository(request.question)
        tools.search_repository("follow up")
        return ResearchAgentResult(
            answer=ResearchAnswer(
                question=request.question,
                summary="unreachable",
                confidence=0,
                insufficient_evidence=True,
            )
        )


def test_mvp_change_questions_return_bounded_change_targets(tmp_path: Path) -> None:
    records = load_records(Path("eval/mvp_change_questions.json"))
    repository = RepositoryIdentity(
        name="sample",
        root_path=tmp_path,
        branch="main",
        commit_hash="abc123",
    )

    for record in records:
        service = BoundedResearchService(
            database=FixedDatabase(
                _results_for_record(repository, record.relevant_files)
            ),
            agent=BudgetLimitedAgent(),
        )

        run = service.run(
            repository=repository,
            request=ResearchRequest(
                question=record.question,
                mode=RagMode.CHANGE,
                budget=ResearchBudget(
                    max_searches=1,
                    max_file_reads=1,
                    max_total_tool_calls=2,
                ),
            ),
        )

        assert run.answer.insufficient_evidence is False
        assert run.answer.evidence
        assert run.answer.change_targets
        assert {target.path for target in run.answer.change_targets}.intersection(
            record.relevant_files
        )
        assert run.trace.error_type == "ResearchBudgetExceeded"


def _results_for_record(
    repository: RepositoryIdentity,
    relevant_files: list[str],
) -> list[SearchResult]:
    return [
        SearchResult(
            chunk=ParsedChunk(
                chunk_id=f"{path}:symbol",
                repository_id=repository.repository_id,
                commit_hash=repository.commit_hash,
                path=path,
                language="python",
                chunk_type="function",
                symbol=Path(path).stem,
                start_line=1,
                end_line=3,
                content=f"def {Path(path).stem}():\n    pass\n",
                content_hash=f"hash-{path}",
            ),
            score=1.0,
        )
        for path in relevant_files
    ]
