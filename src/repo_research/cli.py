"""Command line interface for repository ingestion, retrieval, and direct RAG."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from repo_research import runtime
from repo_research.config import Settings
from repo_research.evaluation import evaluate_records, load_records, write_report
from repo_research.ingestion import discover_repository, parse_files
from repo_research.models import (
    IngestSummary,
    RagAnswer,
    RagMode,
    RagRequest,
    RepositoryIdentity,
    RetrievalMode,
    SearchQuery,
)
from repo_research.rag import (
    RepositorySearcher,
    evaluate_answers_from_dataset,
    write_answer_evaluation_report,
)


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
    return parser


def main() -> None:
    """Run one CLI command and emit structured JSON for people and scripts."""
    arguments = build_parser().parse_args()
    settings = Settings()
    root_path = (arguments.path or settings.repository_root).resolve()
    database = runtime.create_database(settings)
    if arguments.command in {"ask", "ingest"}:
        if arguments.command == "ask":
            _report_step("starting qdrant")
            _start_qdrant_if_available()
            _report_step("ingesting repository")
        repository, files = discover_repository(root_path, settings.max_file_size_bytes)
        parsed_files = parse_files(files, repository)
        index_updated = bool(parsed_files.chunks or not parsed_files.skipped_files)
        if index_updated:
            database.replace(repository.repository_id, parsed_files.chunks)
        summary = IngestSummary(
            repository=repository,
            indexed_chunks=len(parsed_files.chunks),
            skipped_files=parsed_files.skipped_files,
            index_updated=index_updated,
        )
        if arguments.command == "ingest":
            print(json.dumps(summary.model_dump(mode="json"), indent=2))
            return
        _report_step(f"indexed {summary.indexed_chunks} chunks")
        _report_step("running direct rag")
        answer = _run_direct_rag(
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
        print(json.dumps(answer.model_dump(mode="json"), indent=2))
        return

    repository, _ = discover_repository(root_path, settings.max_file_size_bytes)
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
        answer = _run_direct_rag(
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
        print(json.dumps(answer.model_dump(mode="json"), indent=2))
        return

    if arguments.command == "evaluate-answers":
        model = runtime.create_answer_model(settings)
        service = runtime.create_direct_rag_service(
            settings=settings,
            database=database,
            generator=model,
        )
        answer_results = evaluate_answers_from_dataset(
            service=service,
            judge=model,
            repository=repository,
            dataset=arguments.dataset,
            retrieval_mode=RetrievalMode(arguments.retrieval_mode)
            if arguments.retrieval_mode
            else settings.retrieval_mode,
            limit=arguments.limit or settings.answer_evaluation_limit,
        )
        write_answer_evaluation_report(answer_results, arguments.output)
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
) -> RagAnswer:
    service = runtime.create_direct_rag_service(
        settings=settings,
        database=database,
        generator=runtime.create_answer_model(settings),
    )
    return service.answer(
        repository=repository,
        request=RagRequest(
            question=question,
            repository_path=root_path,
            mode=mode,
            retrieval_mode=retrieval_mode,
            limit=limit,
        ),
    )


def _start_qdrant_if_available() -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "qdrant"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _report_step(message: str) -> None:
    sys.stderr.write(f"[repo-research] {message}\n")
