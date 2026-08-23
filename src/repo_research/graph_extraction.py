"""Deterministic repository relationship extraction."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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
from repo_research.models import ParsedChunk, RepositoryIdentity

EXTRACTOR_VERSION = "1.0"


@dataclass(frozen=True)
class ExtractionIndex:
    """Lookup tables used for conservative local relationship resolution."""

    modules_by_name: dict[str, GraphNode]
    symbols_by_qualified_name: dict[str, GraphNode]
    symbols_by_short_name: dict[str, tuple[GraphNode, ...]]
    config_keys_by_name: dict[str, GraphNode]


def build_repository_graph(
    repository: RepositoryIdentity,
    files: list[Path],
    chunks: list[ParsedChunk],
    *,
    skipped_files: list[str] | None = None,
    warnings: list[str] | None = None,
) -> RepositoryGraph:
    """Build a deterministic graph for one parsed repository revision."""
    nodes = _build_nodes(repository, chunks)
    index = _build_index(nodes)
    edges = _build_edges(repository, files, chunks, nodes, index)
    ordered_nodes = sorted(nodes.values(), key=lambda node: node.id)
    ordered_edges = sorted(
        edges.values(),
        key=lambda edge: (edge.source, edge.type.value, edge.target, edge.method),
    )
    manifest = GraphManifest(
        schema_version=GRAPH_SCHEMA_VERSION,
        repository_id=repository.repository_id,
        repository_name=repository.name,
        branch=repository.branch,
        commit_hash=repository.commit_hash,
        generated_at=datetime.now(UTC),
        node_count=len(ordered_nodes),
        edge_count=len(ordered_edges),
        node_counts_by_label=dict(
            sorted(
                Counter(
                    label.value for node in ordered_nodes for label in node.labels
                ).items()
            )
        ),
        edge_counts_by_type=dict(
            sorted(Counter(edge.type.value for edge in ordered_edges).items())
        ),
        extractor_versions={"graph_extraction": EXTRACTOR_VERSION},
        skipped_files=sorted(skipped_files or []),
        warnings=sorted(warnings or []),
    )
    return RepositoryGraph(manifest=manifest, nodes=ordered_nodes, edges=ordered_edges)


def _build_nodes(
    repository: RepositoryIdentity, chunks: list[ParsedChunk]
) -> dict[str, GraphNode]:
    nodes: dict[str, GraphNode] = {}
    repo_id = stable_node_id(
        repository.repository_id,
        repository.commit_hash,
        "Repository",
        repository.repository_id,
    )
    nodes[repo_id] = GraphNode(
        id=repo_id,
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        labels=[NodeLabel.REPOSITORY],
        key=repository.repository_id,
        path=".",
    )
    for chunk in sorted(
        chunks, key=lambda item: (item.path, item.start_line, item.chunk_id)
    ):
        file_node = _file_node(repository, chunk.path)
        nodes.setdefault(file_node.id, file_node)
        module_name = _module_name(chunk.path)
        if chunk.language == "python" and chunk.chunk_type == "module":
            module_node = _module_node(
                repository, chunk.path, module_name, chunk.chunk_id
            )
            nodes[module_node.id] = module_node
        elif chunk.symbol:
            node = _symbol_node(repository, chunk, module_name)
            nodes[node.id] = node
        if chunk.chunk_type == "configuration" or chunk.language == "python":
            for key in _config_keys_from_text(chunk.content):
                config_node = _config_node(repository, chunk.path, key, chunk.chunk_id)
                nodes[config_node.id] = config_node
    return nodes


def _build_index(nodes: dict[str, GraphNode]) -> ExtractionIndex:
    modules_by_name: dict[str, GraphNode] = {}
    for node in nodes.values():
        module = node.properties.get("module")
        if NodeLabel.MODULE in node.labels and isinstance(module, str):
            modules_by_name[module] = node
    symbols_by_qualified_name = {
        str(node.properties["qualified_name"]): node
        for node in nodes.values()
        if any(
            label in node.labels
            for label in (NodeLabel.CLASS, NodeLabel.FUNCTION, NodeLabel.METHOD)
        )
        and isinstance(node.properties.get("qualified_name"), str)
    }
    short: dict[str, list[GraphNode]] = {}
    for node in symbols_by_qualified_name.values():
        if node.symbol:
            short.setdefault(node.symbol.split(".")[-1], []).append(node)
    config_keys_by_name = {
        node.key: node for node in nodes.values() if NodeLabel.CONFIG_KEY in node.labels
    }
    return ExtractionIndex(
        modules_by_name=modules_by_name,
        symbols_by_qualified_name=symbols_by_qualified_name,
        symbols_by_short_name={key: tuple(value) for key, value in short.items()},
        config_keys_by_name=config_keys_by_name,
    )


def _build_edges(
    repository: RepositoryIdentity,
    files: list[Path],
    chunks: list[ParsedChunk],
    nodes: dict[str, GraphNode],
    index: ExtractionIndex,
) -> dict[tuple[str, str, RelationshipType, str], GraphEdge]:
    edges: dict[tuple[str, str, RelationshipType, str], GraphEdge] = {}
    repo_node = nodes[
        stable_node_id(
            repository.repository_id,
            repository.commit_hash,
            "Repository",
            repository.repository_id,
        )
    ]
    chunks_by_path = {
        chunk.path: chunk for chunk in chunks if chunk.chunk_type == "module"
    }
    for chunk in chunks:
        file_node = nodes[_file_node(repository, chunk.path).id]
        _add_edge(
            repository,
            edges,
            repo_node,
            file_node,
            RelationshipType.CONTAINS,
            "repository_file",
            1.0,
        )
        target = _node_for_chunk(repository, chunk, nodes)
        if target is not None:
            _add_edge(
                repository,
                edges,
                file_node,
                target,
                RelationshipType.CONTAINS,
                "parsed_chunk",
                1.0,
            )
    for path in sorted(files):
        if path.suffix != ".py":
            continue
        relative_path = path.relative_to(repository.root_path).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError:
            continue
        module = index.modules_by_name.get(_module_name(relative_path))
        if module is None:
            module_chunk = chunks_by_path.get(relative_path)
            if module_chunk is not None:
                module = _node_for_chunk(repository, module_chunk, nodes)
        if module is None:
            continue
        imported_symbols = _imported_symbols(repository, tree, relative_path, index)
        for imported in imported_symbols.values():
            _add_edge(
                repository,
                edges,
                module,
                imported,
                RelationshipType.IMPORTS,
                "ast_import",
                1.0,
            )
        for ast_node in ast.walk(tree):
            if not isinstance(
                ast_node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                continue
            current = _current_symbol_node(relative_path, ast_node, index)
            if current is None:
                continue
            if isinstance(ast_node, ast.ClassDef):
                _class_edges(
                    repository, edges, ast_node, current, imported_symbols, index
                )
            _decorator_edges(
                repository, edges, ast_node, current, imported_symbols, index
            )
            for child in ast.walk(ast_node):
                _reference_edges(
                    repository, edges, child, current, imported_symbols, index
                )
        if _is_test_path(relative_path):
            _test_edges(repository, edges, module, tree, imported_symbols, index)
    return edges


def _class_edges(
    repository: RepositoryIdentity,
    edges: dict[tuple[str, str, RelationshipType, str], GraphEdge],
    ast_node: ast.ClassDef,
    current: GraphNode,
    imported_symbols: dict[str, GraphNode],
    index: ExtractionIndex,
) -> None:
    for base in ast_node.bases:
        target = _resolve_expr(base, imported_symbols, index)
        if target is not None:
            _add_edge(
                repository,
                edges,
                current,
                target,
                RelationshipType.INHERITS,
                "ast_base",
                1.0,
            )


def _decorator_edges(
    repository: RepositoryIdentity,
    edges: dict[tuple[str, str, RelationshipType, str], GraphEdge],
    ast_node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    current: GraphNode,
    imported_symbols: dict[str, GraphNode],
    index: ExtractionIndex,
) -> None:
    for decorator in ast_node.decorator_list:
        target = _resolve_expr(decorator, imported_symbols, index)
        if target is not None:
            _add_edge(
                repository,
                edges,
                current,
                target,
                RelationshipType.DECORATED_BY,
                "ast_decorator",
                1.0,
            )


def _reference_edges(
    repository: RepositoryIdentity,
    edges: dict[tuple[str, str, RelationshipType, str], GraphEdge],
    ast_node: ast.AST,
    current: GraphNode,
    imported_symbols: dict[str, GraphNode],
    index: ExtractionIndex,
) -> None:
    if isinstance(ast_node, ast.Call):
        target = _resolve_expr(ast_node.func, imported_symbols, index)
        if target is not None and target.id != current.id:
            _add_edge(
                repository,
                edges,
                current,
                target,
                RelationshipType.CALLS,
                "ast_resolved_call",
                1.0,
            )
    if isinstance(ast_node, ast.Name) and isinstance(ast_node.ctx, ast.Load):
        config = index.config_keys_by_name.get(ast_node.id)
        if config is not None:
            _add_edge(
                repository,
                edges,
                current,
                config,
                RelationshipType.READS_CONFIG,
                "ast_config_read",
                1.0,
            )
        target = _resolve_short_name(ast_node.id, imported_symbols, index)
        if target is not None and target.id != current.id:
            _add_edge(
                repository,
                edges,
                current,
                target,
                RelationshipType.REFERENCES,
                "ast_name",
                0.9,
            )
    if isinstance(ast_node, ast.Constant) and isinstance(ast_node.value, str):
        config = index.config_keys_by_name.get(ast_node.value)
        if config is not None:
            _add_edge(
                repository,
                edges,
                current,
                config,
                RelationshipType.READS_CONFIG,
                "ast_config_string",
                0.8,
            )


def _test_edges(
    repository: RepositoryIdentity,
    edges: dict[tuple[str, str, RelationshipType, str], GraphEdge],
    module: GraphNode,
    tree: ast.Module,
    imported_symbols: dict[str, GraphNode],
    index: ExtractionIndex,
) -> None:
    del index
    for imported in imported_symbols.values():
        _add_edge(
            repository,
            edges,
            module,
            imported,
            RelationshipType.TESTS,
            "test_import",
            1.0,
        )
    for ast_node in ast.walk(tree):
        if isinstance(ast_node, ast.Name):
            target = imported_symbols.get(ast_node.id)
            if target is not None:
                _add_edge(
                    repository,
                    edges,
                    module,
                    target,
                    RelationshipType.TESTS,
                    "test_symbol_reference",
                    0.8,
                )


def _imported_symbols(
    repository: RepositoryIdentity,
    tree: ast.Module,
    path: str,
    index: ExtractionIndex,
) -> dict[str, GraphNode]:
    imported: dict[str, GraphNode] = {}
    current_module = _module_name(path)
    for ast_node in tree.body:
        if isinstance(ast_node, ast.Import):
            for alias in ast_node.names:
                module_node = index.modules_by_name.get(alias.name)
                if module_node is not None:
                    imported[alias.asname or alias.name.split(".")[-1]] = module_node
        elif isinstance(ast_node, ast.ImportFrom):
            module_name = _resolve_import_from(current_module, ast_node)
            module_node = index.modules_by_name.get(module_name)
            if module_node is not None:
                imported[ast_node.module or module_name.rsplit(".", 1)[-1]] = (
                    module_node
                )
            for alias in ast_node.names:
                if alias.name == "*":
                    continue
                qualified = f"{module_name}.{alias.name}"
                target = index.symbols_by_qualified_name.get(
                    qualified
                ) or index.modules_by_name.get(qualified)
                if target is not None:
                    imported[alias.asname or alias.name] = target
    del repository
    return imported


def _current_symbol_node(
    path: str, ast_node: ast.AST, index: ExtractionIndex
) -> GraphNode | None:
    if not isinstance(ast_node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return None
    module = _module_name(path)
    candidates = [
        node
        for qualified, node in index.symbols_by_qualified_name.items()
        if qualified == f"{module}.{ast_node.name}"
        or qualified.endswith(f".{ast_node.name}")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_expr(
    expr: ast.AST, imported_symbols: dict[str, GraphNode], index: ExtractionIndex
) -> GraphNode | None:
    if isinstance(expr, ast.Call):
        return _resolve_expr(expr.func, imported_symbols, index)
    if isinstance(expr, ast.Name):
        return _resolve_short_name(expr.id, imported_symbols, index)
    if isinstance(expr, ast.Attribute):
        dotted = ast.unparse(expr)
        return index.symbols_by_qualified_name.get(dotted) or _resolve_short_name(
            expr.attr, imported_symbols, index
        )
    return None


def _resolve_short_name(
    name: str, imported_symbols: dict[str, GraphNode], index: ExtractionIndex
) -> GraphNode | None:
    imported = imported_symbols.get(name)
    if imported is not None:
        return imported
    candidates = index.symbols_by_short_name.get(name, ())
    if len(candidates) == 1:
        return candidates[0]
    return None


def _node_for_chunk(
    repository: RepositoryIdentity, chunk: ParsedChunk, nodes: dict[str, GraphNode]
) -> GraphNode | None:
    if chunk.language == "python" and chunk.chunk_type == "module":
        return nodes.get(
            _module_node(
                repository, chunk.path, _module_name(chunk.path), chunk.chunk_id
            ).id
        )
    if chunk.symbol:
        return nodes.get(_symbol_node(repository, chunk, _module_name(chunk.path)).id)
    return None


def _file_node(repository: RepositoryIdentity, path: str) -> GraphNode:
    return GraphNode(
        id=stable_node_id(
            repository.repository_id, repository.commit_hash, "File", path
        ),
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        labels=[NodeLabel.FILE],
        key=path,
        path=path,
    )


def _module_node(
    repository: RepositoryIdentity, path: str, module_name: str, chunk_id: str | None
) -> GraphNode:
    return GraphNode(
        id=stable_node_id(
            repository.repository_id, repository.commit_hash, "Module", module_name
        ),
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        labels=[NodeLabel.MODULE],
        key=module_name,
        path=path,
        chunk_id=chunk_id,
        properties={"module": module_name},
    )


def _symbol_node(
    repository: RepositoryIdentity, chunk: ParsedChunk, module_name: str
) -> GraphNode:
    assert chunk.symbol is not None
    label = {
        "class": NodeLabel.CLASS,
        "function": NodeLabel.FUNCTION,
        "method": NodeLabel.METHOD,
    }.get(chunk.chunk_type, NodeLabel.SYMBOL)
    qualified_name = f"{module_name}.{chunk.symbol}"
    return GraphNode(
        id=stable_node_id(
            repository.repository_id,
            repository.commit_hash,
            label.value,
            qualified_name,
        ),
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        labels=[NodeLabel.SYMBOL, label] if label is not NodeLabel.SYMBOL else [label],
        key=qualified_name,
        path=chunk.path,
        symbol=chunk.symbol,
        chunk_id=chunk.chunk_id,
        properties={"qualified_name": qualified_name},
    )


def _config_node(
    repository: RepositoryIdentity, path: str, key: str, chunk_id: str | None
) -> GraphNode:
    return GraphNode(
        id=stable_node_id(
            repository.repository_id, repository.commit_hash, "ConfigKey", key
        ),
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        labels=[NodeLabel.CONFIG_KEY],
        key=key,
        path=path,
        chunk_id=chunk_id,
    )


def _add_edge(
    repository: RepositoryIdentity,
    edges: dict[tuple[str, str, RelationshipType, str], GraphEdge],
    source: GraphNode,
    target: GraphNode,
    relationship: RelationshipType,
    method: str,
    confidence: float,
) -> None:
    key = (source.id, target.id, relationship, method)
    edges[key] = GraphEdge(
        id=stable_edge_id(
            repository.repository_id,
            repository.commit_hash,
            source.id,
            target.id,
            relationship.value,
            method,
        ),
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        source=source.id,
        target=target.id,
        type=relationship,
        confidence=confidence,
        method=method,
    )


def _module_name(path: str) -> str:
    without_suffix = path.removesuffix(".py").replace("/", ".")
    if without_suffix.startswith("src."):
        without_suffix = without_suffix.removeprefix("src.")
    if without_suffix.endswith(".__init__"):
        without_suffix = without_suffix.removesuffix(".__init__")
    return without_suffix


def _resolve_import_from(current_module: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    parts = current_module.split(".")
    prefix = ".".join(parts[: max(0, len(parts) - node.level)])
    if node.module:
        return f"{prefix}.{node.module}" if prefix else node.module
    return prefix


def _config_keys_from_text(content: str) -> set[str]:
    keys: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return keys
    for ast_node in ast.walk(tree):
        if isinstance(ast_node, ast.Assign):
            for target in ast_node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    keys.add(target.id)
        if (
            isinstance(ast_node, ast.Constant)
            and isinstance(ast_node.value, str)
            and ast_node.value.startswith("RDR_")
        ):
            keys.add(ast_node.value)
    return keys


def _is_test_path(path: str) -> bool:
    return (
        path.startswith("tests/")
        or "/tests/" in path
        or Path(path).name.startswith("test_")
    )
