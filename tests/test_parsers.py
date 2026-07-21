"""Tests for source chunks and their evidence metadata."""

from pathlib import Path

from repo_research.ingestion import parse_file
from repo_research.models import RepositoryIdentity


def _repository(root: Path) -> RepositoryIdentity:
    return RepositoryIdentity(
        name="sample",
        root_path=root,
        branch="main",
        commit_hash="abc123",
    )


def test_python_parser_extracts_imports_symbols_and_line_ranges(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text(
        "import pathlib\n\n"
        "@decorator\n"
        "def top(value: int) -> str:\n"
        '    """Top-level docstring."""\n'
        "    return str(value)\n\n"
        "class Worker:\n"
        '    """Worker docs."""\n\n'
        "    @staticmethod\n"
        "    def run() -> None:\n"
        "        return None\n",
        encoding="utf-8",
    )

    chunks = parse_file(path, _repository(tmp_path))
    by_symbol = {chunk.symbol: chunk for chunk in chunks}

    assert by_symbol["top"].start_line == 4
    assert by_symbol["top"].end_line == 6
    assert by_symbol["top"].context["imports"] == ["import pathlib"]
    assert by_symbol["top"].context["signature"] == "value: int"
    assert by_symbol["top"].context["decorators"] == ["decorator"]
    assert by_symbol["Worker"].context["docstring"] == "Worker docs."
    assert by_symbol["Worker.run"].parent_symbol == "Worker"
    assert by_symbol["Worker.run"].chunk_type == "method"


def test_markdown_parser_preserves_heading_hierarchy(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text("# Guide\nIntro\n## Setup\nInstall\n", encoding="utf-8")

    chunks = parse_file(path, _repository(tmp_path))

    assert [chunk.symbol for chunk in chunks] == ["Guide", "Guide > Setup"]
    assert chunks[1].start_line == 3
    assert chunks[1].end_line == 4


def test_configuration_file_is_preserved_as_one_chunk(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("[service]\nport = 8000\n", encoding="utf-8")

    chunks = parse_file(path, _repository(tmp_path))

    assert len(chunks) == 1
    assert chunks[0].language == "toml"
    assert chunks[0].content == "[service]\nport = 8000\n"
