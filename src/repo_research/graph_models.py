"""Portable repository property-graph models."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, field_validator, model_validator

GRAPH_SCHEMA_VERSION = "1.0"
ScalarProperty = str | int | float | bool


class NodeLabel(StrEnum):
    """Portable graph node labels."""

    REPOSITORY = "Repository"
    FILE = "File"
    MODULE = "Module"
    SYMBOL = "Symbol"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    CONFIG_KEY = "ConfigKey"


class RelationshipType(StrEnum):
    """Portable graph relationship types."""

    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    REFERENCES = "REFERENCES"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    DECORATED_BY = "DECORATED_BY"
    TESTS = "TESTS"
    READS_CONFIG = "READS_CONFIG"


class GraphNode(BaseModel):
    """One portable property-graph node for a repository revision."""

    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    labels: list[NodeLabel] = Field(min_length=1)
    key: str = Field(min_length=1)
    path: str = Field(min_length=1)
    symbol: str | None = None
    chunk_id: str | None = Field(default=None, min_length=1)
    properties: dict[str, ScalarProperty] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_node_id(cls, value: str) -> str:
        """Require portable node ID prefixes."""
        if not value.startswith("node:"):
            raise ValueError("node id must start with node:")
        return value

    @field_validator("properties", mode="before")
    @classmethod
    def validate_scalar_properties(cls, value: object) -> object:
        """Reject nested graph property values with an explicit message."""
        if isinstance(value, dict):
            for property_value in value.values():
                if not isinstance(property_value, str | int | float | bool):
                    raise ValueError("graph properties must be scalar values")
        return value


class GraphEdge(BaseModel):
    """One typed relationship between graph nodes."""

    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    type: RelationshipType
    confidence: float = Field(ge=0, le=1)
    method: str = Field(min_length=1)
    properties: dict[str, ScalarProperty] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_edge_id(cls, value: str) -> str:
        """Require portable edge ID prefixes."""
        if not value.startswith("edge:"):
            raise ValueError("edge id must start with edge:")
        return value

    @field_validator("properties", mode="before")
    @classmethod
    def validate_scalar_properties(cls, value: object) -> object:
        """Reject nested graph property values with an explicit message."""
        if isinstance(value, dict):
            for property_value in value.values():
                if not isinstance(property_value, str | int | float | bool):
                    raise ValueError("graph properties must be scalar values")
        return value


class GraphManifest(BaseModel):
    """Versioned metadata for one repository graph artifact."""

    schema_version: str = GRAPH_SCHEMA_VERSION
    repository_id: str = Field(min_length=1)
    repository_name: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    commit_hash: str = Field(min_length=1)
    generated_at: datetime
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    node_counts_by_label: dict[str, int] = Field(default_factory=dict)
    edge_counts_by_type: dict[str, int] = Field(default_factory=dict)
    extractor_versions: dict[str, str] = Field(default_factory=dict)
    skipped_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GraphSummary(BaseModel):
    """Small printable summary for a graph artifact."""

    schema_version: str
    repository_id: str
    repository_name: str
    branch: str
    commit_hash: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    node_counts_by_label: dict[str, int] = Field(default_factory=dict)
    edge_counts_by_type: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class GraphTraversal(BaseModel):
    """Bounded traversal result from a repository graph."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    relationship_counts: dict[RelationshipType, int] = Field(default_factory=dict)


class RepositoryGraph(BaseModel):
    """Validated graph for exactly one repository revision."""

    manifest: GraphManifest
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> RepositoryGraph:
        """Ensure graph identity, counts, and endpoints are internally consistent."""
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node IDs must be unique")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("graph edge IDs must be unique")
        if self.manifest.node_count != len(self.nodes):
            raise ValueError("manifest node count does not match graph nodes")
        if self.manifest.edge_count != len(self.edges):
            raise ValueError("manifest edge count does not match graph edges")
        nodes_by_id = {node.id: node for node in self.nodes}
        for node in self.nodes:
            if (
                node.repository_id != self.manifest.repository_id
                or node.commit_hash != self.manifest.commit_hash
            ):
                raise ValueError("all nodes must share the same repository revision")
        for edge in self.edges:
            source = nodes_by_id.get(edge.source)
            target = nodes_by_id.get(edge.target)
            if source is None or target is None:
                raise ValueError("graph edges must reference existing endpoints")
            if (
                edge.repository_id != self.manifest.repository_id
                or edge.commit_hash != self.manifest.commit_hash
                or source.repository_id != target.repository_id
                or source.commit_hash != target.commit_hash
            ):
                raise ValueError(
                    "graph edge endpoints must share the same repository revision"
                )
        return self

    def summary(self) -> GraphSummary:
        """Return a compact artifact summary."""
        return GraphSummary(
            schema_version=self.manifest.schema_version,
            repository_id=self.manifest.repository_id,
            repository_name=self.manifest.repository_name,
            branch=self.manifest.branch,
            commit_hash=self.manifest.commit_hash,
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            node_counts_by_label=self.manifest.node_counts_by_label,
            edge_counts_by_type=self.manifest.edge_counts_by_type,
            warnings=self.manifest.warnings,
        )

    def traverse(
        self,
        *,
        start_node_ids: list[str],
        relationship_types: set[RelationshipType] | None = None,
        max_depth: int = 2,
        max_nodes: int = 12,
        min_confidence: float = 0.0,
        direction: str = "outgoing",
    ) -> GraphTraversal:
        """Traverse relationships breadth-first with deterministic caps."""
        if max_depth > 2:
            raise ValueError("graph traversal depth cannot exceed two")
        nodes_by_id = {node.id: node for node in self.nodes}
        adjacency: dict[str, list[GraphEdge]] = {}
        for edge in self.edges:
            if relationship_types is not None and edge.type not in relationship_types:
                continue
            if edge.confidence < min_confidence:
                continue
            if direction in {"outgoing", "both"}:
                adjacency.setdefault(edge.source, []).append(edge)
            if direction in {"incoming", "both"}:
                adjacency.setdefault(edge.target, []).append(edge)
        for edges in adjacency.values():
            edges.sort(
                key=lambda edge: (
                    edge.source,
                    edge.type.value,
                    edge.target,
                    edge.method,
                )
            )

        visited = set(start_node_ids)
        collected_nodes: list[GraphNode] = []
        collected_edges: list[GraphEdge] = []
        relationship_counts: dict[RelationshipType, int] = {}
        frontier: deque[tuple[str, int]] = deque(
            (node_id, 0) for node_id in sorted(start_node_ids)
        )
        while frontier:
            node_id, depth = frontier.popleft()
            if depth >= max_depth:
                continue
            for edge in adjacency.get(node_id, []):
                next_id = edge.target if edge.source == node_id else edge.source
                if next_id in visited or next_id not in nodes_by_id:
                    continue
                if len(collected_nodes) >= max_nodes:
                    return GraphTraversal(
                        nodes=collected_nodes,
                        edges=collected_edges,
                        relationship_counts=relationship_counts,
                    )
                visited.add(next_id)
                collected_edges.append(edge)
                relationship_counts[edge.type] = (
                    relationship_counts.get(edge.type, 0) + 1
                )
                collected_nodes.append(nodes_by_id[next_id])
                frontier.append((next_id, depth + 1))
        return GraphTraversal(
            nodes=collected_nodes,
            edges=collected_edges,
            relationship_counts=relationship_counts,
        )


def stable_node_id(repository_id: str, commit_hash: str, label: str, key: str) -> str:
    """Return a deterministic opaque node ID."""
    identity = "|".join([repository_id, commit_hash, label, key])
    return f"node:{uuid5(NAMESPACE_URL, identity)}"


def stable_edge_id(
    repository_id: str,
    commit_hash: str,
    source: str,
    target: str,
    relationship_type: str,
    method: str,
) -> str:
    """Return a deterministic opaque edge ID."""
    identity = "|".join(
        [repository_id, commit_hash, source, target, relationship_type, method]
    )
    return f"edge:{uuid5(NAMESPACE_URL, identity)}"
