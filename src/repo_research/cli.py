"""Command line interface for repository ingestion, retrieval, and direct RAG."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from repo_research import runtime
from repo_research.answer_evaluation import (
    AnswerEvaluationCandidate,
    audit_evaluation_records,
    dataset_candidates,
    judge_answer_candidates,
    monitored_answer_candidates,
    write_persisted_answer_evaluation_report,
)
from repo_research.config import Settings
from repo_research.evaluation import evaluate_records, load_records, write_report
from repo_research.ingestion import discover_repository, ingest_repository_if_needed
from repo_research.models import (
    EvaluationRunRecord,
    EvaluationRunStatus,
    EvaluationSourceType,
    PersistedEvaluationResult,
    RagMode,
    RagRequest,
    RagRunResult,
    RepositoryIdentity,
    ResearchBudget,
    ResearchRequest,
    ResearchRunResult,
    RetrievalMode,
    RunKind,
    SearchQuery,
)
from repo_research.protocols import RepositorySearcher
from repo_research.rag import AnswerJudge, DirectRagService
from repo_research.research import ResearchAgentRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without executing application work."""
    parser = argparse.ArgumentParser(description="Search a local Python repository")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="parse and index a repository")
    ingest.add_argument("path", type=Path, nargs="?", default=None)
    ask = subparsers.add_parser(
        "ask", help="ingest if needed and answer with grounded direct RAG"
    )
    ask.add_argument("question")
    ask.add_argument("--path", type=Path, default=None)
    ask.add_argument("--mode", choices=[mode.value for mode in RagMode], default="auto")
    ask.add_argument(
        "--retrieval-mode",
        choices=[mode.value for mode in RetrievalMode],
        default=None,
    )
    ask.add_argument("--limit", type=int, default=None)
    search = subparsers.add_parser("search", help="run dense repository search")
    search.add_argument("query")
    search.add_argument("--path", type=Path, default=None)
    search.add_argument("--limit", type=int, default=5)
    search.add_argument(
        "--mode", choices=[mode.value for mode in RetrievalMode], default=None
    )
    evaluate = subparsers.add_parser(
        "evaluate-retrieval", help="evaluate dense, sparse, and hybrid retrieval"
    )
    evaluate.add_argument("--path", type=Path, default=None)
    evaluate.add_argument("--dataset", type=Path, default=Path("eval/development.json"))
    evaluate.add_argument(
        "--output", type=Path, default=Path("eval/results/retrieval-development.json")
    )
    evaluate.add_argument("--limit", type=int, default=5)
    rag = subparsers.add_parser("rag", help="answer with grounded direct RAG")
    rag.add_argument("question")
    rag.add_argument("--path", type=Path, default=None)
    rag.add_argument("--mode", choices=[mode.value for mode in RagMode], default="auto")
    rag.add_argument(
        "--retrieval-mode",
        choices=[mode.value for mode in RetrievalMode],
        default=None,
    )
    rag.add_argument("--limit", type=int, default=None)
    research = subparsers.add_parser(
        "research", help="answer with bounded agentic repository research"
    )
    research.add_argument("question")
    research.add_argument("--path", type=Path, default=None)
    research.add_argument(
        "--mode", choices=[mode.value for mode in RagMode], default="change"
    )
    research.add_argument(
        "--retrieval-mode",
        choices=[mode.value for mode in RetrievalMode],
        default=None,
    )
    research.add_argument("--limit", type=int, default=None)
    research.add_argument("--max-searches", type=int, default=None)
    research.add_argument("--max-file-reads", type=int, default=None)
    research.add_argument("--max-total-tool-calls", type=int, default=None)
    answer_eval = subparsers.add_parser(
        "evaluate-answers", help="evaluate grounded answers with an LLM judge"
    )
    answer_eval.add_argument("--path", type=Path, default=None)
    answer_eval.add_argument(
        "--dataset", type=Path, default=Path("eval/development.json")
    )
    answer_eval.add_argument(
        "--output", type=Path, default=Path("eval/results/answer-development.json")
    )
    answer_eval.add_argument(
        "--retrieval-mode",
        choices=[mode.value for mode in RetrievalMode],
        default=None,
    )
    answer_eval.add_argument("--limit", type=int, default=None)
    answer_eval.add_argument(
        "--source",
        choices=["dataset", "monitored-runs"],
        default="dataset",
    )
    answer_eval.add_argument(
        "--approach",
        choices=["direct", "agentic", "both"],
        default="direct",
        help="answer-generation approach used for dataset source",
    )
    answer_eval.add_argument(
        "--run-kind",
        choices=[run_kind.value for run_kind in RunKind],
        default=None,
        help="optional monitored-runs filter",
    )
    answer_eval.add_argument(
        "--repository-name",
        default=None,
        help="optional monitored-runs repository-name filter",
    )
    answer_eval.add_argument(
        "--request-id",
        action="append",
        default=[],
        help="optional monitored-runs request_id filter; repeat for multiple runs",
    )
    answer_eval.add_argument(
        "--persist",
        action="store_true",
        help="persist evaluation run and result rows to PostgreSQL",
    )
    return parser


def main() -> None:
    """Run one CLI command and emit structured JSON for people and scripts."""
    arguments = build_parser().parse_args()
    settings = Settings()
    root_path = (arguments.path or settings.repository_root).resolve()
    if arguments.command == "evaluate-answers" and arguments.source == "monitored-runs":
        answer_results = _run_monitored_answer_evaluation(
            arguments=arguments,
            settings=settings,
        )
        write_persisted_answer_evaluation_report(answer_results, arguments.output)
        print(
            json.dumps(
                [result.model_dump(mode="json") for result in answer_results],
                indent=2,
            )
        )
        return

    database = runtime.create_database(settings)
    if arguments.command in {"ask", "ingest"}:
        if arguments.command == "ask":
            _report_step("starting qdrant")
            _start_qdrant_if_available()
            _report_step("ingesting repository")
        repository, files = discover_repository(root_path, settings.max_file_size_bytes)
        summary = ingest_repository_if_needed(
            database=database,
            repository=repository,
            files=files,
        )
        if arguments.command == "ingest":
            print(json.dumps(summary.model_dump(mode="json"), indent=2))
            return
        _report_step(f"indexed {summary.indexed_chunks} chunks")
        _report_step("running direct rag")
        run_result = _run_direct_rag(
            database=database,
            repository=repository,
            root_path=root_path,
            settings=settings,
            question=arguments.question,
            mode=RagMode(arguments.mode),
            retrieval_mode=RetrievalMode(arguments.retrieval_mode)
            if arguments.retrieval_mode
            else settings.retrieval_mode,
            limit=arguments.limit or settings.retrieval_limit,
        )
        _report_step("done")
        print(json.dumps(run_result.model_dump(mode="json"), indent=2))
        return

    repository, files = discover_repository(root_path, settings.max_file_size_bytes)
    if arguments.command == "research":
        _report_step("ingesting repository")
        summary = ingest_repository_if_needed(
            database=database,
            repository=repository,
            files=files,
        )
        _report_step(f"indexed {summary.indexed_chunks} chunks")
        _report_step("running agentic research")
        research_run_result = _run_agentic_research(
            database=database,
            agent=runtime.create_research_agent(settings),
            repository=repository,
            root_path=root_path,
            settings=settings,
            question=arguments.question,
            mode=RagMode(arguments.mode),
            retrieval_mode=RetrievalMode(arguments.retrieval_mode)
            if arguments.retrieval_mode
            else settings.retrieval_mode,
            limit=arguments.limit or settings.retrieval_limit,
            budget=ResearchBudget(
                max_searches=arguments.max_searches or settings.research_max_searches,
                max_file_reads=arguments.max_file_reads
                or settings.research_max_file_reads,
                max_total_tool_calls=arguments.max_total_tool_calls
                or settings.research_max_total_tool_calls,
            ),
        )
        _report_step("done")
        print(json.dumps(research_run_result.model_dump(mode="json"), indent=2))
        return

    if arguments.command == "evaluate-retrieval":
        evaluation_results = evaluate_records(
            database=database,
            repository=repository,
            records=load_records(arguments.dataset),
            dataset=arguments.dataset.as_posix(),
            limit=arguments.limit,
        )
        write_report(evaluation_results, arguments.output)
        print(
            json.dumps(
                [result.model_dump(mode="json") for result in evaluation_results],
                indent=2,
            )
        )
        return

    if arguments.command == "rag":
        run_result = _run_direct_rag(
            database=database,
            repository=repository,
            root_path=root_path,
            settings=settings,
            question=arguments.question,
            mode=RagMode(arguments.mode),
            retrieval_mode=RetrievalMode(arguments.retrieval_mode)
            if arguments.retrieval_mode
            else settings.retrieval_mode,
            limit=arguments.limit or settings.retrieval_limit,
        )
        print(json.dumps(run_result.model_dump(mode="json"), indent=2))
        return

    if arguments.command == "evaluate-answers":
        model = runtime.create_answer_model(settings)
        service = runtime.create_direct_rag_service(
            settings=settings,
            database=database,
            generator=model,
        )
        answer_results = _run_unified_answer_evaluation(
            arguments=arguments,
            settings=settings,
            repository=repository,
            database=database,
            direct_service=service,
            judge=model,
        )
        write_persisted_answer_evaluation_report(answer_results, arguments.output)
        print(
            json.dumps(
                [result.model_dump(mode="json") for result in answer_results],
                indent=2,
            )
        )
        return

    results = database.search(
        SearchQuery(
            text=arguments.query,
            repository_id=repository.repository_id,
            commit_hash=repository.commit_hash,
            limit=arguments.limit,
            mode=RetrievalMode(arguments.mode)
            if arguments.mode
            else settings.retrieval_mode,
        )
    )
    print(json.dumps([result.model_dump(mode="json") for result in results], indent=2))


def _run_direct_rag(
    *,
    database: RepositorySearcher,
    repository: RepositoryIdentity,
    root_path: Path,
    settings: Settings,
    question: str,
    mode: RagMode,
    retrieval_mode: RetrievalMode,
    limit: int,
) -> RagRunResult:
    service = runtime.create_direct_rag_service(
        settings=settings,
        database=database,
        generator=runtime.create_answer_model(settings),
    )
    return service.run(
        repository=repository,
        request=RagRequest(
            question=question,
            repository_path=root_path,
            mode=mode,
            retrieval_mode=retrieval_mode,
            limit=limit,
        ),
    )


def _run_agentic_research(
    *,
    database: RepositorySearcher,
    agent: ResearchAgentRunner,
    repository: RepositoryIdentity,
    root_path: Path,
    settings: Settings,
    question: str,
    mode: RagMode,
    retrieval_mode: RetrievalMode,
    limit: int,
    budget: ResearchBudget,
) -> ResearchRunResult:
    service = runtime.create_bounded_research_service(
        settings=settings,
        database=database,
        agent=agent,
    )
    return service.run(
        repository=repository,
        request=ResearchRequest(
            question=question,
            repository_path=root_path,
            mode=mode,
            retrieval_mode=retrieval_mode,
            retrieval_limit=limit,
            budget=budget,
        ),
    )


def _run_unified_answer_evaluation(
    *,
    arguments: argparse.Namespace,
    settings: Settings,
    repository: RepositoryIdentity,
    database: RepositorySearcher,
    direct_service: DirectRagService,
    judge: AnswerJudge,
) -> list[PersistedEvaluationResult]:
    retrieval_mode = (
        RetrievalMode(arguments.retrieval_mode)
        if arguments.retrieval_mode
        else settings.retrieval_mode
    )
    limit = arguments.limit or settings.answer_evaluation_limit
    source_type = (
        EvaluationSourceType.MONITORED_RUNS
        if arguments.source == "monitored-runs"
        else EvaluationSourceType.DATASET
    )
    if source_type is EvaluationSourceType.DATASET:
        records = load_records(arguments.dataset)
        audit = audit_evaluation_records({arguments.dataset.as_posix(): records})
        _report_step(
            f"loaded {audit.record_count} evaluation records across "
            f"{audit.question_type_counts}"
        )
        candidates = dataset_candidates(
            direct_service=direct_service,
            research_service=runtime.create_bounded_research_service(
                settings=settings,
                database=database,
                agent=runtime.create_research_agent(settings),
            )
            if arguments.approach in {"agentic", "both"}
            else None,
            repository=repository,
            records=records,
            retrieval_mode=retrieval_mode,
            limit=limit,
            approaches=_evaluation_approaches(arguments.approach),
        )
        source_label = arguments.dataset.as_posix()
    else:
        recording_store = runtime.create_recording_store(settings)
        candidates = monitored_answer_candidates(
            source=recording_store,
            limit=limit,
            run_kind=RunKind(arguments.run_kind) if arguments.run_kind else None,
            repository_name=arguments.repository_name,
        )
        source_label = "monitored-runs"

    evaluation_run = EvaluationRunRecord(
        source_type=source_type,
        source_label=source_label,
        judge_model=settings.openai_judge_model,
        started_at=datetime.now(UTC),
    )
    evaluation_store = (
        runtime.create_recording_store(settings) if arguments.persist else None
    )
    if evaluation_store is not None:
        evaluation_store.record_evaluation_run(
            evaluation_run.model_copy(update={"status": EvaluationRunStatus.RUNNING})
        )
    try:
        results = judge_answer_candidates(
            candidates=candidates,
            judge=judge,
            evaluation_run_id=evaluation_run.evaluation_run_id,
        )
        if evaluation_store is not None:
            for result in results:
                evaluation_store.record_evaluation_result(result)
            evaluation_store.record_evaluation_run(
                evaluation_run.model_copy(
                    update={
                        "status": EvaluationRunStatus.COMPLETED,
                        "completed_at": datetime.now(UTC),
                        "error_message": None,
                    }
                )
            )
    except Exception as error:
        if evaluation_store is not None:
            evaluation_store.record_evaluation_run(
                evaluation_run.model_copy(
                    update={
                        "status": EvaluationRunStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "error_message": str(error),
                    }
                )
            )
        raise
    return results


def _run_monitored_answer_evaluation(
    *,
    arguments: argparse.Namespace,
    settings: Settings,
) -> list[PersistedEvaluationResult]:
    if not settings.telemetry_enabled or settings.postgres_dsn is None:
        raise SystemExit(
            "RDR_POSTGRES_DSN is required for evaluate-answers --source monitored-runs"
        )

    limit = arguments.limit or settings.answer_evaluation_limit
    recording_store = runtime.create_recording_store(settings)
    request_ids = arguments.request_id or None
    candidates = monitored_answer_candidates(
        source=recording_store,
        limit=limit,
        run_kind=RunKind(arguments.run_kind) if arguments.run_kind else None,
        repository_name=arguments.repository_name,
        request_ids=request_ids,
    )
    _report_step(f"loaded {len(candidates)} monitored answer snapshots")
    if not candidates:
        return []
    return _judge_and_optionally_persist_answer_candidates(
        candidates=candidates,
        judge=runtime.create_answer_model(settings),
        settings=settings,
        source_type=EvaluationSourceType.MONITORED_RUNS,
        source_label="monitored-runs",
        persist=arguments.persist,
    )


def _judge_and_optionally_persist_answer_candidates(
    *,
    candidates: list[AnswerEvaluationCandidate],
    judge: AnswerJudge,
    settings: Settings,
    source_type: EvaluationSourceType,
    source_label: str,
    persist: bool,
) -> list[PersistedEvaluationResult]:
    evaluation_run = EvaluationRunRecord(
        source_type=source_type,
        source_label=source_label,
        judge_model=settings.openai_judge_model,
        started_at=datetime.now(UTC),
    )
    evaluation_store = runtime.create_recording_store(settings) if persist else None
    if evaluation_store is not None:
        evaluation_store.record_evaluation_run(
            evaluation_run.model_copy(update={"status": EvaluationRunStatus.RUNNING})
        )
    try:
        _report_step(
            f"judging {len(candidates)} answers with {settings.openai_judge_model}"
        )
        results = judge_answer_candidates(
            candidates=candidates,
            judge=judge,
            evaluation_run_id=evaluation_run.evaluation_run_id,
        )
        if evaluation_store is not None:
            for result in results:
                evaluation_store.record_evaluation_result(result)
            evaluation_store.record_evaluation_run(
                evaluation_run.model_copy(
                    update={
                        "status": EvaluationRunStatus.COMPLETED,
                        "completed_at": datetime.now(UTC),
                        "error_message": None,
                    }
                )
            )
            _report_step(f"persisted {len(results)} evaluation results")
    except Exception as error:
        if evaluation_store is not None:
            evaluation_store.record_evaluation_run(
                evaluation_run.model_copy(
                    update={
                        "status": EvaluationRunStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "error_message": str(error),
                    }
                )
            )
        raise
    return results


def _evaluation_approaches(value: str) -> list[RunKind]:
    if value == "both":
        return [RunKind.DIRECT, RunKind.AGENTIC]
    if value == "agentic":
        return [RunKind.AGENTIC]
    return [RunKind.DIRECT]


def _start_qdrant_if_available() -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "qdrant"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _report_step(message: str) -> None:
    sys.stderr.write(f"[repo-research] {message}\n")
