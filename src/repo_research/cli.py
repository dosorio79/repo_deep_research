"""Command line interface for M1 local repository indexing and search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qdrant_client import QdrantClient

from repo_research.config import Settings
from repo_research.db import RepositoryDatabase, local_embedder
from repo_research.ingestion import discover_repository, parse_files
from repo_research.models import SearchQuery


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
    return parser


def main() -> None:
    """Run one CLI command and emit structured JSON for people and scripts."""
    arguments = build_parser().parse_args()
    settings = Settings()
    root_path = (arguments.path or settings.repository_root).resolve()
    database = _create_database(settings)
    if arguments.command == "ingest":
        repository, files = discover_repository(root_path, settings.max_file_size_bytes)
        chunks = parse_files(files, repository)
        database.replace(repository.repository_id, chunks)
        print(
            json.dumps(
                {
                    "repository": repository.model_dump(mode="json"),
                    "indexed_chunks": len(chunks),
                },
                indent=2,
            )
        )
        return

    repository, _ = discover_repository(root_path, settings.max_file_size_bytes)
    results = database.search(
        SearchQuery(
            text=arguments.query,
            repository_id=repository.repository_id,
            limit=arguments.limit,
        )
    )
    print(json.dumps([result.model_dump(mode="json") for result in results], indent=2))


def _create_database(settings: Settings) -> RepositoryDatabase:
    return RepositoryDatabase(
        client=QdrantClient(url=settings.qdrant_url),
        collection_name=settings.qdrant_collection,
        embedding_dimension=settings.embedding_dimension,
        embed=local_embedder(settings.embedding_model, settings.embedding_batch_size),
    )
