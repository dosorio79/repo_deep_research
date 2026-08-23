"""Tests for portable repository graph models."""

from datetime import UTC, datetime

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


def test_graph_ids_are_stable_and_commit_scoped() -> None:
    first = stable_node_id("repo-1", "abc123", "Symbol", "src/app.py:run")
    second = stable_node_id("repo-1", "abc123", "Symbol", "src/app.py:run")
    other_commit = stable_node_id("repo-1", "def456", "Symbol", "src/app.py:run")

    assert first == second
    assert first.startswith("node:")
    assert first != other_commit
    assert stable_edge_id("repo-1", "abc123", first, other_commit, "CALLS", "ast")


def test_properties_must_be_scalar() -> None:
    with pytest.raises(ValueError, match="scalar"):
        GraphNode(
            id="node:1",
            repository_id="repo-1",
            commit_hash="abc123",
            labels=[NodeLabel.FILE],
            key="src/app.py",
            path="src/app.py",
            properties={"nested": ["bad"]},  # type: ignore[dict-item]
        )


def test_repository_graph_rejects_cross_revision_edges() -> None:
    source = _node("source", commit_hash="abc123")
    target = _node("target", commit_hash="def456")

    with pytest.raises(ValueError, match="same repository revision"):
        RepositoryGraph(
            manifest=_manifest(commit_hash="abc123", node_count=2, edge_count=1),
            nodes=[source, target],
            edges=[
                GraphEdge(
                    id="edge:1",
                    repository_id="repo-1",
                    commit_hash="abc123",
                    source=source.id,
                    target=target.id,
                    type=RelationshipType.CALLS,
                    confidence=1.0,
                    method="ast_call",
                )
            ],
        )


def test_repository_graph_traverses_breadth_first_with_caps() -> None:
    start = _node("start")
    middle = _node("middle")
    end = _node("end")
    graph = RepositoryGraph(
        manifest=_manifest(node_count=3, edge_count=2),
        nodes=[start, middle, end],
        edges=[
            _edge(start, middle, RelationshipType.IMPORTS),
            _edge(middle, end, RelationshipType.CALLS),
        ],
    )

    traversal = graph.traverse(
        start_node_ids=[start.id],
        relationship_types={RelationshipType.IMPORTS, RelationshipType.CALLS},
        max_depth=2,
        max_nodes=3,
        min_confidence=0.5,
    )

    assert [node.key for node in traversal.nodes] == ["middle", "end"]
    assert traversal.relationship_counts == {
        RelationshipType.CALLS: 1,
        RelationshipType.IMPORTS: 1,
    }


def test_graph_serializes_portable_relationship_shape() -> None:
    source = _node("source")
    target = _node("target")
    edge = _edge(source, target, RelationshipType.IMPORTS)

    assert source.model_dump(mode="json")["labels"] == ["File"]
    assert edge.model_dump(mode="json")["type"] == "IMPORTS"
    assert edge.model_dump(mode="json")["source"] == source.id
    assert edge.model_dump(mode="json")["target"] == target.id


def _node(key: str, *, commit_hash: str = "abc123") -> GraphNode:
    return GraphNode(
        id=stable_node_id("repo-1", commit_hash, "File", key),
        repository_id="repo-1",
        commit_hash=commit_hash,
        labels=[NodeLabel.FILE],
        key=key,
        path=f"{key}.py",
    )


def _edge(
    source: GraphNode, target: GraphNode, relationship: RelationshipType
) -> GraphEdge:
    return GraphEdge(
        id=stable_edge_id(
            "repo-1",
            source.commit_hash,
            source.id,
            target.id,
            relationship.value,
            "test",
        ),
        repository_id="repo-1",
        commit_hash=source.commit_hash,
        source=source.id,
        target=target.id,
        type=relationship,
        confidence=1.0,
        method="test",
    )


def _manifest(
    *, commit_hash: str = "abc123", node_count: int = 0, edge_count: int = 0
) -> GraphManifest:
    return GraphManifest(
        schema_version=GRAPH_SCHEMA_VERSION,
        repository_id="repo-1",
        repository_name="repo",
        branch="main",
        commit_hash=commit_hash,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        node_count=node_count,
        edge_count=edge_count,
    )
