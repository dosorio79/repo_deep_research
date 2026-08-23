"""Tests for coordinated chunk and graph ingestion."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from repo_research.graph_models import (
    GRAPH_SCHEMA_VERSION,
    GraphManifest,
    GraphNode,
    GraphSummary,
    NodeLabel,
    RepositoryGraph,
    stable_node_id,
)
from repo_research.ingestion import discover_repository, ingest_repository_if_needed
from repo_research.models import ParsedChunk


class RecordingIndexer:
    def __init__(self, events: list[str], indexed_count: int = 0) -> None:
        self.events = events
        self.indexed_count = indexed_count

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        del repository_id, chunks
        self.events.append("qdrant_replace")

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        del repository_id, commit_hash
        return self.indexed_count


class RecordingGraphStore:
    def __init__(self, events: list[str], exists: bool = False) -> None:
        self.events = events
        self._exists = exists

    def write(self, graph: RepositoryGraph) -> GraphSummary:
        self.events.append("graph_write")
        return graph.summary()

    def load(self, repository_id: str, commit_hash: str) -> RepositoryGraph:
        return sample_graph(repository_id=repository_id, commit_hash=commit_hash)

    def exists(self, repository_id: str, commit_hash: str) -> bool:
        del repository_id, commit_hash
        return self._exists


class FailingGraphStore(RecordingGraphStore):
    def write(self, graph: RepositoryGraph) -> GraphSummary:
        del graph
        self.events.append("graph_write")
        raise ValueError("graph failed")


def test_ingestion_builds_graph_before_replacing_index(tmp_path: Path) -> None:
    _write(tmp_path / "app.py", "def run() -> None:\n    pass\n")
    commit_test_repo(tmp_path)
    repository, files = discover_repository(tmp_path, 1_000_000)
    events: list[str] = []

    summary = ingest_repository_if_needed(
        database=RecordingIndexer(events),
        graph_store=RecordingGraphStore(events),
        repository=repository,
        files=files,
    )

    assert events == ["graph_write", "qdrant_replace"]
    assert summary.graph_updated is True
    assert summary.graph_nodes > 0
    assert summary.graph_edges > 0


def test_ingestion_reuse_requires_index_and_graph(tmp_path: Path) -> None:
    _write(tmp_path / "app.py", "def run() -> None:\n    pass\n")
    commit_test_repo(tmp_path)
    repository, files = discover_repository(tmp_path, 1_000_000)
    events: list[str] = []

    summary = ingest_repository_if_needed(
        database=RecordingIndexer(events, indexed_count=3),
        graph_store=RecordingGraphStore(events, exists=True),
        repository=repository,
        files=files,
    )

    assert events == []
    assert summary.index_updated is False
    assert summary.graph_updated is False
    assert summary.indexed_chunks == 3
    assert summary.graph_nodes == 1
    assert summary.graph_edges == 0


def test_graph_failure_leaves_index_untouched(tmp_path: Path) -> None:
    _write(tmp_path / "app.py", "def run() -> None:\n    pass\n")
    repository, files = discover_repository(tmp_path, 1_000_000)
    events: list[str] = []

    with pytest.raises(ValueError, match="graph failed"):
        ingest_repository_if_needed(
            database=RecordingIndexer(events),
            graph_store=FailingGraphStore(events),
            repository=repository,
            files=files,
        )

    assert events == ["graph_write"]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sample_graph(repository_id: str, commit_hash: str) -> RepositoryGraph:
    node = GraphNode(
        id=stable_node_id(repository_id, commit_hash, "File", "app.py"),
        repository_id=repository_id,
        commit_hash=commit_hash,
        labels=[NodeLabel.FILE],
        key="app.py",
        path="app.py",
    )
    return RepositoryGraph(
        manifest=GraphManifest(
            schema_version=GRAPH_SCHEMA_VERSION,
            repository_id=repository_id,
            repository_name="repo",
            branch="main",
            commit_hash=commit_hash,
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            node_count=1,
            edge_count=0,
        ),
        nodes=[node],
        edges=[],
    )


def commit_test_repo(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
    )
