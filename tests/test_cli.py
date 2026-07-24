"""Tests for the command-line boundary."""

import json
import sys
from pathlib import Path

import pytest

from repo_research import cli
from repo_research.cli import build_parser
from repo_research.models import ParsedChunk


def test_cli_parses_search_request() -> None:
    arguments = build_parser().parse_args(["search", "where is cost calculated?"])

    assert arguments.command == "search"
    assert arguments.query == "where is cost calculated?"
    assert arguments.limit == 5


class FakeDatabase:
    """Capture CLI indexing calls without connecting to Qdrant."""

    def __init__(self) -> None:
        self.replacements: list[tuple[str, int]] = []

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        self.replacements.append((repository_id, len(chunks)))


class FakeSettings:
    """Minimal settings used by the CLI ingestion test."""

    repository_root = Path(".")
    max_file_size_bytes = 1_048_576


def test_cli_ingest_emits_skipped_file_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "valid.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "invalid.py").write_text("def broken(:\n", encoding="utf-8")
    database = FakeDatabase()
    monkeypatch.setattr(cli, "Settings", FakeSettings)

    def create_database(_: object) -> FakeDatabase:
        return database

    monkeypatch.setattr(cli, "_create_database", create_database)
    monkeypatch.setattr(sys, "argv", ["repo-research", "ingest", str(tmp_path)])

    cli.main()

    result = json.loads(capsys.readouterr().out)
    assert database.replacements[0][1] == 1
    assert result["indexed_chunks"] == 1
    assert result["index_updated"] is True
    assert result["skipped_files"][0]["path"] == "invalid.py"


def test_cli_keeps_the_existing_index_when_every_file_fails_to_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "invalid.py").write_text("def broken(:\n", encoding="utf-8")
    database = FakeDatabase()
    monkeypatch.setattr(cli, "Settings", FakeSettings)

    def create_database(_: object) -> FakeDatabase:
        return database

    monkeypatch.setattr(cli, "_create_database", create_database)
    monkeypatch.setattr(sys, "argv", ["repo-research", "ingest", str(tmp_path)])

    cli.main()

    result = json.loads(capsys.readouterr().out)
    assert database.replacements == []
    assert result["indexed_chunks"] == 0
    assert result["index_updated"] is False
