"""Tests for deterministic repository relationship extraction."""

from pathlib import Path

from repo_research.graph_extraction import build_repository_graph
from repo_research.graph_models import RelationshipType
from repo_research.ingestion import discover_repository, parse_files


def test_extracts_supported_relationships_from_python_repo(tmp_path: Path) -> None:
    _write_graph_fixture(tmp_path)
    repository, files = discover_repository(tmp_path, 1_000_000)
    parsed = parse_files(files, repository)

    graph = build_repository_graph(repository, files, parsed.chunks)
    relationships = {(edge.type, edge.method) for edge in graph.edges}

    assert (RelationshipType.CONTAINS, "parsed_chunk") in relationships
    assert (RelationshipType.IMPORTS, "ast_import") in relationships
    assert (RelationshipType.INHERITS, "ast_base") in relationships
    assert (RelationshipType.DECORATED_BY, "ast_decorator") in relationships
    assert (RelationshipType.CALLS, "ast_resolved_call") in relationships
    assert (RelationshipType.READS_CONFIG, "ast_config_read") in relationships
    assert (RelationshipType.TESTS, "test_import") in relationships


def test_extraction_is_deterministic(tmp_path: Path) -> None:
    _write_graph_fixture(tmp_path)
    repository, files = discover_repository(tmp_path, 1_000_000)
    parsed = parse_files(files, repository)

    first = build_repository_graph(repository, files, parsed.chunks)
    second = build_repository_graph(repository, files, parsed.chunks)

    assert [node.model_dump(mode="json") for node in first.nodes] == [
        node.model_dump(mode="json") for node in second.nodes
    ]
    assert [edge.model_dump(mode="json") for edge in first.edges] == [
        edge.model_dump(mode="json") for edge in second.edges
    ]


def test_ambiguous_short_name_call_is_omitted(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/sample/a.py",
        "def duplicate() -> None:\n    pass\n",
    )
    _write(
        tmp_path / "src/sample/b.py",
        "def duplicate() -> None:\n    pass\n",
    )
    _write(
        tmp_path / "src/sample/c.py",
        "def run() -> None:\n    duplicate()\n",
    )
    repository, files = discover_repository(tmp_path, 1_000_000)
    parsed = parse_files(files, repository)

    graph = build_repository_graph(repository, files, parsed.chunks)

    assert not any(
        edge.type is RelationshipType.CALLS and edge.method == "ast_resolved_call"
        for edge in graph.edges
    )


def _write_graph_fixture(root: Path) -> None:
    _write(root / "src/sample/config.py", 'RETRIEVAL_LIMIT = "RDR_RETRIEVAL_LIMIT"\n')
    _write(
        root / "src/sample/service.py",
        """
from sample.config import RETRIEVAL_LIMIT


def traced(func):
    return func


class BaseService:
    pass


class SearchService(BaseService):
    @traced
    def run(self) -> str:
        return helper(RETRIEVAL_LIMIT)


def helper(value: str) -> str:
    return value
""".strip()
        + "\n",
    )
    _write(
        root / "tests/test_service.py",
        """
from sample.service import SearchService


def test_service() -> None:
    assert SearchService().run() == "RDR_RETRIEVAL_LIMIT"
""".strip()
        + "\n",
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
