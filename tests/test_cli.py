"""Tests for the command-line boundary."""

import json
import sys
from pathlib import Path

import pytest

from repo_research import cli, runtime
from repo_research.cli import build_parser
from repo_research.models import (
    ParsedChunk,
    RagMode,
    RagRequest,
    RagRunResult,
    ResearchAnswer,
    ResearchRequest,
    ResearchRunResult,
    SearchResult,
)
from repo_research.rag import AnswerGenerationResult
from repo_research.research import ResearchAgentResult


def test_cli_parses_search_request() -> None:
    arguments = build_parser().parse_args(
        ["search", "where is cost calculated?", "--mode", "hybrid"]
    )

    assert arguments.command == "search"
    assert arguments.query == "where is cost calculated?"
    assert arguments.limit == 5
    assert arguments.mode == "hybrid"


def test_cli_parses_retrieval_evaluation_request() -> None:
    arguments = build_parser().parse_args(
        ["evaluate-retrieval", "--dataset", "eval/held_out.json", "--limit", "10"]
    )

    assert arguments.command == "evaluate-retrieval"
    assert arguments.dataset == Path("eval/held_out.json")
    assert arguments.limit == 10


def test_cli_parses_rag_request() -> None:
    arguments = build_parser().parse_args(
        [
            "rag",
            "where is configuration validated?",
            "--mode",
            "locate",
            "--retrieval-mode",
            "dense",
        ]
    )

    assert arguments.command == "rag"
    assert arguments.question == "where is configuration validated?"
    assert arguments.mode == "locate"
    assert arguments.retrieval_mode == "dense"


def test_cli_parses_research_request() -> None:
    arguments = build_parser().parse_args(
        [
            "research",
            "which modules change for bounded research?",
            "--mode",
            "change",
            "--retrieval-mode",
            "dense",
            "--max-searches",
            "2",
        ]
    )

    assert arguments.command == "research"
    assert arguments.question == "which modules change for bounded research?"
    assert arguments.mode == "change"
    assert arguments.retrieval_mode == "dense"
    assert arguments.max_searches == 2


def test_cli_parses_ask_request() -> None:
    arguments = build_parser().parse_args(
        [
            "ask",
            "where is configuration validated?",
            "--mode",
            "locate",
            "--retrieval-mode",
            "dense",
        ]
    )

    assert arguments.command == "ask"
    assert arguments.question == "where is configuration validated?"
    assert arguments.mode == "locate"
    assert arguments.retrieval_mode == "dense"


def test_cli_parses_answer_evaluation_request() -> None:
    arguments = build_parser().parse_args(
        ["evaluate-answers", "--dataset", "eval/held_out.json", "--limit", "3"]
    )

    assert arguments.command == "evaluate-answers"
    assert arguments.dataset == Path("eval/held_out.json")
    assert arguments.limit == 3


class FakeDatabase:
    """Capture CLI indexing calls without connecting to Qdrant."""

    def __init__(self) -> None:
        self.replacements: list[tuple[str, int]] = []
        self.results: list[SearchResult] = []

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        self.replacements.append((repository_id, len(chunks)))

    def search(self, query: object) -> list[SearchResult]:
        return self.results


class FakeSettings:
    """Minimal settings used by the CLI ingestion test."""

    repository_root = Path(".")
    max_file_size_bytes = 1_048_576
    retrieval_mode = "dense"
    retrieval_limit = 5
    answer_evaluation_limit = 5
    research_max_searches = 3
    research_max_file_reads = 5
    research_max_total_tool_calls = 8
    openai_model = "gpt-5-mini"
    openai_judge_model = "gpt-5.1"


class FakeOpenAIModel:
    """Fake answer model used by CLI tests."""

    def generate_answer(
        self,
        *,
        request: RagRequest,
        evidence_context: str,
    ) -> AnswerGenerationResult:
        raise AssertionError("no evidence should skip model generation")


class FakeResearchAgent:
    """Fake agentic research model used by CLI tests."""

    def run_research(
        self,
        *,
        request: ResearchRequest,
        tools: object,
    ) -> ResearchAgentResult:
        del tools
        return ResearchAgentResult(
            answer=ResearchAnswer(
                question=request.question,
                mode=request.mode,
                summary="Insufficient repository evidence to produce a plan.",
                confidence=0.0,
                insufficient_evidence=True,
            )
        )


def test_cli_rag_emits_grounded_answer_without_live_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase()
    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(runtime, "create_database", lambda _: database)
    monkeypatch.setattr(runtime, "create_answer_model", lambda _: FakeOpenAIModel())
    monkeypatch.setattr(
        sys,
        "argv",
        ["repo-research", "rag", "where is missing logic?", "--path", "."],
    )

    cli.main()

    result = RagRunResult.model_validate_json(capsys.readouterr().out)
    assert result.answer.mode is RagMode.LOCATE
    assert result.answer.insufficient_evidence is True
    assert result.trace.retrieved_chunk_count == 0


def test_cli_ask_ingests_then_emits_grounded_answer_without_live_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "valid.py").write_text("value = 1\n", encoding="utf-8")
    database = FakeDatabase()
    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(runtime, "create_database", lambda _: database)
    monkeypatch.setattr(runtime, "create_answer_model", lambda _: FakeOpenAIModel())
    monkeypatch.setattr(cli, "_start_qdrant_if_available", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["repo-research", "ask", "where is missing logic?", "--path", str(tmp_path)],
    )

    cli.main()

    captured = capsys.readouterr()
    result = RagRunResult.model_validate_json(captured.out)
    assert database.replacements[0][1] == 1
    assert result.answer.insufficient_evidence is True
    assert result.trace.tool_call_count == 0
    assert "[repo-research] ingesting repository" in captured.err
    assert "[repo-research] running direct rag" in captured.err


def test_cli_research_emits_agentic_response_without_live_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase()
    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(runtime, "create_database", lambda _: database)
    monkeypatch.setattr(runtime, "create_research_agent", lambda _: FakeResearchAgent())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repo-research",
            "research",
            "which modules change?",
            "--path",
            ".",
            "--max-searches",
            "1",
        ],
    )

    cli.main()

    result = ResearchRunResult.model_validate_json(capsys.readouterr().out)
    assert result.answer.mode is RagMode.CHANGE
    assert result.answer.insufficient_evidence is True
    assert result.trace.tool_call_count == 0
    assert database.replacements


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

    monkeypatch.setattr(runtime, "create_database", create_database)
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

    monkeypatch.setattr(runtime, "create_database", create_database)
    monkeypatch.setattr(sys, "argv", ["repo-research", "ingest", str(tmp_path)])

    cli.main()

    result = json.loads(capsys.readouterr().out)
    assert database.replacements == []
    assert result["indexed_chunks"] == 0
    assert result["index_updated"] is False
