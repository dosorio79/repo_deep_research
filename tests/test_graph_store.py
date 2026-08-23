"""Tests for versioned JSONL repository graph artifacts."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from repo_research.graph_models import (
    GRAPH_SCHEMA_VERSION,
    GraphEdge,
    GraphManifest,
    GraphNode,
    NodeLabel,
    RelationshipType,
    RepositoryGraph,
    stable_edge_id,
    stable_node_id,
)
from repo_research.graph_store import GraphArtifactStore


def test_graph_store_round_trip_uses_commit_scoped_jsonl(tmp_path: Path) -> None:
    store = GraphArtifactStore(tmp_path)
    graph = sample_graph()

    summary = store.write(graph)
    artifact = tmp_path / "repo-1" / "abc123"

    assert sorted(path.name for path in artifact.iterdir()) == [
        "edges.jsonl",
        "manifest.json",
        "nodes.jsonl",
    ]
    assert store.load("repo-1", "abc123") == graph
    assert summary.schema_version == GRAPH_SCHEMA_VERSION
    assert summary.node_count == 2
    assert summary.edge_count == 1


def test_graph_store_reuses_existing_valid_artifact_without_rewriting(
    tmp_path: Path,
) -> None:
    store = GraphArtifactStore(tmp_path)
    graph = sample_graph()
    store.write(graph)
    before = {
        path.name: path.read_bytes()
        for path in (tmp_path / "repo-1" / "abc123").iterdir()
    }

    store.write(graph)

    after = {
        path.name: path.read_bytes()
        for path in (tmp_path / "repo-1" / "abc123").iterdir()
    }
    assert after == before


def test_graph_store_rejects_path_escape_identity(tmp_path: Path) -> None:
    store = GraphArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="path separators"):
        store.load("../repo", "abc123")


def test_graph_store_reports_missing_artifact_as_unavailable(
    tmp_path: Path,
) -> None:
    store = GraphArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="artifact is missing"):
        store.load("repo-1", "abc123")

    assert store.exists("repo-1", "abc123") is False


def test_graph_store_rejects_manifest_count_mismatch(tmp_path: Path) -> None:
    store = GraphArtifactStore(tmp_path)
    store.write(sample_graph())
    manifest_path = tmp_path / "repo-1" / "abc123" / "manifest.json"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            '"node_count": 2', '"node_count": 3'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="count"):
        store.load("repo-1", "abc123")


def sample_graph(commit_hash: str = "abc123") -> RepositoryGraph:
    source = GraphNode(
        id=stable_node_id("repo-1", commit_hash, "File", "src/app.py"),
        repository_id="repo-1",
        commit_hash=commit_hash,
        labels=[NodeLabel.FILE],
        key="src/app.py",
        path="src/app.py",
        chunk_id="chunk-a",
    )
    target = GraphNode(
        id=stable_node_id("repo-1", commit_hash, "File", "tests/test_app.py"),
        repository_id="repo-1",
        commit_hash=commit_hash,
        labels=[NodeLabel.FILE],
        key="tests/test_app.py",
        path="tests/test_app.py",
        chunk_id="chunk-b",
    )
    edge = GraphEdge(
        id=stable_edge_id(
            "repo-1",
            commit_hash,
            source.id,
            target.id,
            RelationshipType.TESTS.value,
            "test",
        ),
        repository_id="repo-1",
        commit_hash=commit_hash,
        source=source.id,
        target=target.id,
        type=RelationshipType.TESTS,
        confidence=1.0,
        method="test",
    )
    return RepositoryGraph(
        manifest=GraphManifest(
            schema_version=GRAPH_SCHEMA_VERSION,
            repository_id="repo-1",
            repository_name="repo",
            branch="main",
            commit_hash=commit_hash,
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            node_count=2,
            edge_count=1,
            node_counts_by_label={"File": 2},
            edge_counts_by_type={"TESTS": 1},
            extractor_versions={"graph_extraction": "1.0"},
            skipped_files=["bad.py"],
            warnings=["warning"],
        ),
        nodes=[source, target],
        edges=[edge],
    )
