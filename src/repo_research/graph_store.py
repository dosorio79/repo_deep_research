"""Atomic JSONL persistence for repository graph artifacts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pydantic import TypeAdapter

from repo_research.graph_models import (
    GRAPH_SCHEMA_VERSION,
    GraphEdge,
    GraphManifest,
    GraphNode,
    GraphSummary,
    RepositoryGraph,
)

_NODE_LIST = TypeAdapter(list[GraphNode])
_EDGE_LIST = TypeAdapter(list[GraphEdge])


class GraphArtifactStore:
    """Persist immutable graph artifacts by repository revision."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, graph: RepositoryGraph) -> GraphSummary:
        """Write a graph artifact atomically or reuse an existing valid artifact."""
        target = self._artifact_dir(
            graph.manifest.repository_id, graph.manifest.commit_hash
        )
        if target.exists():
            return self.load(
                graph.manifest.repository_id,
                graph.manifest.commit_hash,
            ).summary()
        staging = target.with_name(f".{target.name}.staging")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            self._write_graph_files(staging, graph)
            staged_graph = self._load_from_dir(staging, validate_path=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(target)
            return staged_graph.summary()
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def load(self, repository_id: str, commit_hash: str) -> RepositoryGraph:
        """Load and validate one repository graph artifact."""
        return self._load_from_dir(self._artifact_dir(repository_id, commit_hash))

    def exists(self, repository_id: str, commit_hash: str) -> bool:
        """Return whether a valid graph artifact exists."""
        try:
            self.load(repository_id, commit_hash)
        except (OSError, ValueError):
            return False
        return True

    def _artifact_dir(self, repository_id: str, commit_hash: str) -> Path:
        _validate_path_part(repository_id)
        _validate_path_part(commit_hash)
        return self._root / repository_id / commit_hash

    def _write_graph_files(self, artifact: Path, graph: RepositoryGraph) -> None:
        (artifact / "manifest.json").write_text(
            json.dumps(graph.manifest.model_dump(mode="json"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_jsonl(
            artifact / "nodes.jsonl",
            [node.model_dump(mode="json") for node in graph.nodes],
        )
        _write_jsonl(
            artifact / "edges.jsonl",
            [edge.model_dump(mode="json") for edge in graph.edges],
        )

    def _load_from_dir(
        self, artifact: Path, *, validate_path: bool = True
    ) -> RepositoryGraph:
        manifest = GraphManifest.model_validate_json(
            (artifact / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.schema_version != GRAPH_SCHEMA_VERSION:
            raise ValueError("unsupported graph schema version")
        nodes = _NODE_LIST.validate_python(_read_jsonl(artifact / "nodes.jsonl"))
        edges = _EDGE_LIST.validate_python(_read_jsonl(artifact / "edges.jsonl"))
        graph = RepositoryGraph(manifest=manifest, nodes=nodes, edges=edges)
        if validate_path and (
            artifact.name != manifest.commit_hash
            or artifact.parent.name != manifest.repository_id
        ):
            raise ValueError(
                "graph artifact path does not match manifest repository revision"
            )
        return graph


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[object]:
    rows: list[object] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _validate_path_part(value: str) -> None:
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError("repository graph identity cannot contain path separators")
