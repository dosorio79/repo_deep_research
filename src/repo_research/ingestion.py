"""Discover a local repository and turn supported files into evidence chunks."""

from __future__ import annotations

import ast
import subprocess
from hashlib import sha256
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from pathspec import PathSpec
from pathspec.patterns.gitwildmatch import GitWildMatchPattern

from repo_research.models import (
    IngestionIssue,
    IngestSummary,
    ParsedChunk,
    ParsedFiles,
    RepositoryIdentity,
    create_chunk,
)
from repo_research.protocols import RepositoryIndexer

SUPPORTED_SUFFIXES = {".json", ".md", ".py", ".toml", ".yaml", ".yml"}
IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


def materialize_repository_address(address: str, cache_dir: Path) -> Path:
    """Return a local repository path for either a path or public GitHub URL."""
    stripped = address.strip()
    if not stripped:
        raise ValueError("repository address is required")
    parsed = urlparse(stripped)
    if parsed.scheme in {"http", "https"}:
        return _clone_github_repository(stripped, parsed, cache_dir)
    if parsed.scheme:
        message = "only local paths and public GitHub HTTPS URLs are supported"
        raise ValueError(message)
    return Path(stripped).expanduser().resolve()


def discover_repository(
    root_path: Path, max_file_size_bytes: int
) -> tuple[RepositoryIdentity, list[Path]]:
    """Return repository identity and supported, readable source files."""
    root = root_path.resolve()
    if not root.is_dir():
        message = f"repository path is not a directory: {root}"
        raise ValueError(message)

    repository = RepositoryIdentity(
        name=root.name,
        root_path=root,
        branch=_git_value(root, "branch", ["rev-parse", "--abbrev-ref", "HEAD"]),
        commit_hash=_git_value(root, "commit", ["rev-parse", "HEAD"]),
    )
    gitignore = _read_gitignore(root)
    files = [
        path
        for path in root.rglob("*")
        if _is_eligible(path, root, gitignore, max_file_size_bytes)
    ]
    return repository, sorted(files)


def _clone_github_repository(
    address: str, parsed_url: ParseResult, cache_dir: Path
) -> Path:
    hostname = parsed_url.hostname
    path = parsed_url.path
    if hostname != "github.com" or not path:
        message = "only public github.com repository URLs are supported"
        raise ValueError(message)
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2:
        message = "GitHub URL must include owner and repository name"
        raise ValueError(message)
    owner, repo = parts[0], parts[1].removesuffix(".git")
    cache_key = sha256(address.encode()).hexdigest()[:16]
    target = (cache_dir / f"{owner}-{repo}-{cache_key}").resolve()
    if target.exists():
        if not (target / ".git").is_dir():
            message = (
                f"repository cache path exists but is not a git checkout: {target}"
            )
            raise ValueError(message)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", address, str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = _subprocess_error_message(error)
        message = f"could not clone repository URL: {detail}"
        raise ValueError(message) from error
    return target


def _subprocess_error_message(error: OSError | subprocess.CalledProcessError) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        return (error.stderr or error.stdout or str(error)).strip()
    return str(error)


def parse_files(paths: list[Path], repository: RepositoryIdentity) -> ParsedFiles:
    """Parse files, retaining successful chunks when individual files fail."""
    chunks: list[ParsedChunk] = []
    skipped_files: list[IngestionIssue] = []
    for path in paths:
        try:
            chunks.extend(parse_file(path, repository))
        except (OSError, SyntaxError, UnicodeError) as error:
            skipped_files.append(
                IngestionIssue(
                    path=path.relative_to(repository.root_path).as_posix(),
                    error_type=type(error).__name__,
                    message=_error_message(error),
                )
            )
    return ParsedFiles(chunks=chunks, skipped_files=skipped_files)


def ingest_repository_if_needed(
    *,
    database: RepositoryIndexer,
    repository: RepositoryIdentity,
    files: list[Path],
) -> IngestSummary:
    """Parse and index a repository revision unless it is already indexed."""
    existing_chunk_count = database.indexed_chunk_count(
        repository.repository_id,
        repository.commit_hash,
    )
    if can_reuse_index(repository.commit_hash, existing_chunk_count):
        return IngestSummary(
            repository=repository,
            indexed_chunks=existing_chunk_count,
            skipped_files=[],
            index_updated=False,
        )
    parsed_files = parse_files(files, repository)
    index_updated = bool(parsed_files.chunks or not parsed_files.skipped_files)
    if index_updated:
        database.replace(repository.repository_id, parsed_files.chunks)
    return IngestSummary(
        repository=repository,
        indexed_chunks=len(parsed_files.chunks),
        skipped_files=parsed_files.skipped_files,
        index_updated=index_updated,
    )


def can_reuse_index(commit_hash: str, indexed_chunk_count: int) -> bool:
    """Return whether a previously indexed commit can be reused."""
    return indexed_chunk_count > 0 and not commit_hash.startswith("unknown-")


def parse_file(path: Path, repository: RepositoryIdentity) -> list[ParsedChunk]:
    """Parse one file relative to the repository root."""
    source = path.read_text(encoding="utf-8")
    relative_path = path.relative_to(repository.root_path).as_posix()
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _parse_python(source, relative_path, repository)
    if suffix == ".md":
        return _parse_markdown(source, relative_path, repository)
    return [
        create_chunk(
            repository=repository,
            path=relative_path,
            language={
                ".json": "json",
                ".toml": "toml",
                ".yaml": "yaml",
                ".yml": "yaml",
            }[suffix],
            chunk_type="configuration",
            start_line=1,
            end_line=max(1, len(source.splitlines())),
            content=source or " ",
        )
    ]


def _parse_python(
    source: str, path: str, repository: RepositoryIdentity
) -> list[ParsedChunk]:
    tree = ast.parse(source, filename=path)
    lines = source.splitlines(keepends=True)
    imports = [
        ast.unparse(node)
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]
    chunks = _module_chunk(tree, lines, path, repository, imports)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            chunks.extend(_class_chunks(node, lines, path, repository, imports))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            chunks.append(_function_chunk(node, lines, path, repository, imports))
    if not chunks and source.strip():
        chunks.append(
            create_chunk(
                repository=repository,
                path=path,
                language="python",
                chunk_type="module",
                start_line=1,
                end_line=len(lines),
                content=source,
                context={"imports": imports},
            )
        )
    return chunks


def _module_chunk(
    tree: ast.Module,
    lines: list[str],
    path: str,
    repository: RepositoryIdentity,
    imports: list[str],
) -> list[ParsedChunk]:
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom | ast.Expr)
    ]
    if not nodes:
        return []
    start_line = min(node.lineno for node in nodes)
    end_line = max(node.end_lineno or node.lineno for node in nodes)
    return [
        create_chunk(
            repository=repository,
            path=path,
            language="python",
            chunk_type="module",
            start_line=start_line,
            end_line=end_line,
            content=_source_slice(lines, start_line, end_line),
            context={"imports": imports},
        )
    ]


def _class_chunks(
    node: ast.ClassDef,
    lines: list[str],
    path: str,
    repository: RepositoryIdentity,
    imports: list[str],
) -> list[ParsedChunk]:
    end_line = node.end_lineno or node.lineno
    chunks = [
        create_chunk(
            repository=repository,
            path=path,
            language="python",
            chunk_type="class",
            symbol=node.name,
            start_line=node.lineno,
            end_line=end_line,
            content=_source_slice(lines, node.lineno, end_line),
            context={
                "imports": imports,
                "decorators": [ast.unparse(item) for item in node.decorator_list],
                "docstring": ast.get_docstring(node) or "",
            },
        )
    ]
    chunks.extend(
        _function_chunk(item, lines, path, repository, imports, node.name)
        for item in node.body
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
    )
    return chunks


def _function_chunk(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    path: str,
    repository: RepositoryIdentity,
    imports: list[str],
    parent_symbol: str | None = None,
) -> ParsedChunk:
    end_line = node.end_lineno or node.lineno
    symbol = f"{parent_symbol}.{node.name}" if parent_symbol else node.name
    return create_chunk(
        repository=repository,
        path=path,
        language="python",
        chunk_type="method" if parent_symbol else "function",
        symbol=symbol,
        parent_symbol=parent_symbol,
        start_line=node.lineno,
        end_line=end_line,
        content=_source_slice(lines, node.lineno, end_line),
        context={
            "imports": imports,
            "signature": ast.unparse(node.args),
            "decorators": [ast.unparse(item) for item in node.decorator_list],
            "docstring": ast.get_docstring(node) or "",
        },
    )


def _parse_markdown(
    source: str, path: str, repository: RepositoryIdentity
) -> list[ParsedChunk]:
    lines = source.splitlines(keepends=True)
    headings = [
        (index, len(line) - len(line.lstrip("#")), line.lstrip("#").strip())
        for index, line in enumerate(lines)
        if line.startswith("#") and line.lstrip("#").startswith(" ")
    ]
    if not headings:
        return [
            create_chunk(
                repository=repository,
                path=path,
                language="markdown",
                chunk_type="document",
                start_line=1,
                end_line=max(1, len(lines)),
                content=source or " ",
            )
        ]

    chunks: list[ParsedChunk] = []
    hierarchy: list[tuple[int, str]] = []
    for position, (start, level, title) in enumerate(headings):
        hierarchy = [item for item in hierarchy if item[0] < level]
        hierarchy.append((level, title))
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        chunks.append(
            create_chunk(
                repository=repository,
                path=path,
                language="markdown",
                chunk_type="heading",
                symbol=" > ".join(item[1] for item in hierarchy),
                start_line=start + 1,
                end_line=max(start + 1, end),
                content="".join(lines[start:end]),
                context={"heading_hierarchy": [item[1] for item in hierarchy]},
            )
        )
    return chunks


def _git_value(root: Path, label: str, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return f"unknown-{label}"
    return result.stdout.strip() or f"unknown-{label}"


def _read_gitignore(root: Path) -> PathSpec:
    gitignore_path = root / ".gitignore"
    if not gitignore_path.is_file():
        return PathSpec([])
    return PathSpec.from_lines(
        GitWildMatchPattern,
        gitignore_path.read_text(encoding="utf-8").splitlines(),
    )


def _is_eligible(
    path: Path, root: Path, gitignore: PathSpec, max_file_size_bytes: int
) -> bool:
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return False
    relative_path = path.relative_to(root)
    if any(part in IGNORED_DIRECTORY_NAMES for part in relative_path.parts):
        return False
    if gitignore.match_file(relative_path.as_posix()):
        return False
    if path.stat().st_size > max_file_size_bytes:
        return False
    return b"\x00" not in path.read_bytes()[:8_192]


def _source_slice(lines: list[str], start_line: int, end_line: int) -> str:
    return "".join(lines[start_line - 1 : end_line])


def _error_message(error: OSError | SyntaxError | UnicodeError) -> str:
    if isinstance(error, SyntaxError):
        return error.msg
    return str(error)
