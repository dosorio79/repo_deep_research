"""Command line interface for M1 local repository indexing and search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qdrant_client import QdrantClient

from repo_research.config import Settings
from repo_research.db import RepositoryDatabase, local_embedder, local_sparse_embedder
from repo_research.evaluation import evaluate_records, load_records, write_report
from repo_research.ingestion import discover_repository, parse_files
from repo_research.models import IngestSummary, RetrievalMode, SearchQuery


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without executing application work."""
    parser = argparse.ArgumentParser(description="Search a local Python repository")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="parse and index a repository")
    ingest.add_argument("path", type=Path, nargs="?", default=None)
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
    return parser


def main() -> None:
    """Run one CLI command and emit structured JSON for people and scripts."""
    arguments = build_parser().parse_args()
    settings = Settings()
    root_path = (arguments.path or settings.repository_root).resolve()
    database = _create_database(settings)
    if arguments.command == "ingest":
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
        print(json.dumps(summary.model_dump(mode="json"), indent=2))
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


def _create_database(settings: Settings) -> RepositoryDatabase:
    return RepositoryDatabase(
        client=QdrantClient(url=settings.qdrant_url),
        collection_name=settings.qdrant_collection,
        embedding_dimension=settings.embedding_dimension,
        dense_embed=local_embedder(
            settings.embedding_model, settings.embedding_batch_size
        ),
        sparse_embed=local_sparse_embedder(
            settings.sparse_embedding_model, settings.embedding_batch_size
        ),
    )
