"""Tests for the command-line boundary."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from repo_research import cli, runtime
from repo_research.cli import build_parser
from repo_research.config import Settings
from repo_research.graph_models import (
    GraphManifest,
    GraphNode,
    NodeLabel,
    RepositoryGraph,
    stable_node_id,
)
from repo_research.models import (
    EvaluationResult,
    ParsedChunk,
    RagMode,
    RagRequest,
    RagRunResult,
    RepositoryIdentity,
    ResearchAnswer,
    ResearchRequest,
    ResearchRunResult,
    RetrievalEvaluationSummary,
    RetrievalMode,
    RunKind,
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
        [
            "evaluate-retrieval",
            "--dataset",
            "eval/held_out.json",
            "--limit",
            "10",
            "--persist",
            "--source-label",
            "datapeek held-out",
            "--selected-mode",
            "hybrid",
        ]
    )

    assert arguments.command == "evaluate-retrieval"
    assert arguments.dataset == Path("eval/held_out.json")
    assert arguments.limit == 10
    assert arguments.persist is True
    assert arguments.source_label == "datapeek held-out"
    assert arguments.selected_mode == "hybrid"


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
        [
            "evaluate-answers",
            "--dataset",
            "eval/held_out.json",
            "--limit",
            "3",
            "--source",
            "dataset",
            "--approach",
            "both",
            "--workers",
            "6",
            "--persist",
        ]
    )

    assert arguments.command == "evaluate-answers"
    assert arguments.dataset == Path("eval/held_out.json")
    assert arguments.limit == 3
    assert arguments.source == "dataset"
    assert arguments.approach == "both"
    assert arguments.workers == 6
    assert arguments.persist is True


def test_cli_parses_monitored_answer_evaluation_request() -> None:
    arguments = build_parser().parse_args(
        [
            "evaluate-answers",
            "--source",
            "monitored-runs",
            "--run-kind",
            "agentic",
            "--repository-name",
            "repo",
            "--request-id",
            "request-1",
            "--request-id",
            "request-2",
            "--limit",
            "10",
        ]
    )

    assert arguments.command == "evaluate-answers"
    assert arguments.source == "monitored-runs"
    assert arguments.run_kind == "agentic"
    assert arguments.repository_name == "repo"
    assert arguments.request_id == ["request-1", "request-2"]
    assert arguments.limit == 10


def test_cli_persists_retrieval_evaluation_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeRetrievalEvaluationStore()
    monkeypatch.setattr(runtime, "create_recording_store", lambda _: store)
    results = [
        EvaluationResult(
            dataset="eval/held_out.json",
            mode=RetrievalMode.DENSE,
            limit=5,
            record_count=15,
            file_hit_rate=0.5,
            file_mrr=0.4,
            file_recall=0.3,
            file_precision=0.2,
            symbol_hit_rate=0.1,
        ),
        EvaluationResult(
            dataset="eval/held_out.json",
            mode=RetrievalMode.HYBRID,
            limit=5,
            record_count=15,
            file_hit_rate=0.7,
            file_mrr=0.6,
            file_recall=0.5,
            file_precision=0.4,
            symbol_hit_rate=0.3,
        ),
    ]

    cli._persist_retrieval_evaluation_results(
        results=results,
        settings=cast(Settings, FakePostgresSettings()),
        source_label="datapeek held-out",
        selected_mode=RetrievalMode.HYBRID,
    )

    assert [result.source_label for result in store.results] == [
        "datapeek held-out",
        "datapeek held-out",
    ]
    assert [result.selected for result in store.results] == [False, True]


def test_cli_answer_evaluation_checkpoint_context_scopes_resume(
    tmp_path: Path,
) -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=tmp_path,
        branch="main",
        commit_hash="abc123",
    )

    context = cli._answer_evaluation_checkpoint_context(
        dataset_path=Path("eval/held_out.json"),
        repository=repository,
        retrieval_mode=RetrievalMode.DENSE,
        limit=5,
        approaches=[RunKind.DIRECT, RunKind.AGENTIC],
    )

    assert json.loads(context) == {
        "approaches": ["direct", "agentic"],
        "dataset": "eval/held_out.json",
        "limit": 5,
        "repository_id": repository.repository_id,
        "repository_name": "sample",
        "retrieval_mode": "dense",
    }


class FakeDatabase:
    """Capture CLI indexing calls without connecting to Qdrant."""

    def __init__(self) -> None:
        self.replacements: list[tuple[str, int]] = []
        self.results: list[SearchResult] = []
        self.existing_chunk_count = 0

    def replace(self, repository_id: str, chunks: list[ParsedChunk]) -> None:
        self.replacements.append((repository_id, len(chunks)))

    def search(self, query: object) -> list[SearchResult]:
        return self.results

    def indexed_chunk_count(self, repository_id: str, commit_hash: str) -> int:
        return self.existing_chunk_count


class FakeGraphStore:
    """Capture graph store calls for CLI tests."""

    def __init__(self, *, exists: bool = False) -> None:
        self._exists = exists

    def write(self, graph: object) -> object:
        return graph.summary()  # type: ignore[attr-defined]

    def load(self, repository_id: str, commit_hash: str) -> RepositoryGraph:
        return sample_graph(repository_id=repository_id, commit_hash=commit_hash)

    def exists(self, repository_id: str, commit_hash: str) -> bool:
        del repository_id, commit_hash
        return self._exists


def sample_graph(repository_id: str, commit_hash: str) -> RepositoryGraph:
    node = GraphNode(
        id=stable_node_id(repository_id, commit_hash, "File", "app.py"),
        repository_id=repository_id,
        commit_hash=commit_hash,
        labels=[NodeLabel.FILE],
        key="app.py",
        path="app.py",
    )
    return RepositoryGraph(
        manifest=GraphManifest(
            repository_id=repository_id,
            repository_name="repo",
            branch="main",
            commit_hash=commit_hash,
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            node_count=1,
            edge_count=0,
        ),
        nodes=[node],
        edges=[],
    )


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
    research_max_graph_expansions = 2
    research_max_graph_nodes = 12
    research_max_graph_depth = 2
    openai_model = "gpt-5-mini"
    openai_judge_model = "gpt-5.1"
    postgres_dsn: str | None = None
    telemetry_enabled = True


class FakePostgresSettings(FakeSettings):
    """Settings with PostgreSQL enabled for monitored-evaluation CLI tests."""

    postgres_dsn = "postgresql://example"


class EmptyMonitoredStore:
    """Return no monitored answer snapshots and capture filter arguments."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_answer_snapshots_for_evaluation(
        self,
        *,
        limit: int = 50,
        run_kind: object = None,
        repository_name: str | None = None,
        request_ids: list[str] | None = None,
    ) -> list[object]:
        self.calls.append(
            {
                "limit": limit,
                "run_kind": run_kind,
                "repository_name": repository_name,
                "request_ids": request_ids,
            }
        )
        return []


class FakeRetrievalEvaluationStore:
    """Capture persisted retrieval-evaluation rows."""

    def __init__(self) -> None:
        self.results: list[RetrievalEvaluationSummary] = []

    def record_retrieval_evaluation_result(
        self, result: RetrievalEvaluationSummary
    ) -> None:
        self.results.append(result)


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


def commit_test_repo(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
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


def test_cli_monitored_answer_evaluation_requires_postgres_without_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "Settings", FakeSettings)

    def fail_create_database(_: object) -> FakeDatabase:
        raise AssertionError("monitored evaluation should not create Qdrant database")

    def fail_create_answer_model(_: object) -> FakeOpenAIModel:
        raise AssertionError("missing Postgres DSN should fail before creating a judge")

    monkeypatch.setattr(runtime, "create_database", fail_create_database)
    monkeypatch.setattr(runtime, "create_answer_model", fail_create_answer_model)
    monkeypatch.setattr(
        sys,
        "argv",
        ["repo-research", "evaluate-answers", "--source", "monitored-runs"],
    )

    with pytest.raises(SystemExit, match="RDR_POSTGRES_DSN is required"):
        cli.main()


def test_cli_monitored_answer_evaluation_request_ids_skip_empty_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = EmptyMonitoredStore()
    arguments = build_parser().parse_args(
        [
            "evaluate-answers",
            "--source",
            "monitored-runs",
            "--request-id",
            "request-1",
            "--request-id",
            "request-2",
        ]
    )

    def fail_create_answer_model(_: object) -> FakeOpenAIModel:
        raise AssertionError("empty monitored evaluation should not create a judge")

    monkeypatch.setattr(runtime, "create_recording_store", lambda _: store)
    monkeypatch.setattr(runtime, "create_answer_model", fail_create_answer_model)

    results = cli._run_monitored_answer_evaluation(
        arguments=arguments,
        settings=cast(Settings, FakePostgresSettings()),
    )

    assert results == []
    assert store.calls == [
        {
            "limit": FakePostgresSettings.answer_evaluation_limit,
            "run_kind": None,
            "repository_name": None,
            "request_ids": ["request-1", "request-2"],
        }
    ]


def test_cli_ingest_skips_existing_git_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "invalid.py").write_text("def broken(:\n", encoding="utf-8")
    commit_test_repo(tmp_path)
    database = FakeDatabase()
    database.existing_chunk_count = 3
    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(runtime, "create_database", lambda _: database)
    monkeypatch.setattr(
        runtime, "create_graph_store", lambda _: FakeGraphStore(exists=True)
    )
    monkeypatch.setattr(sys, "argv", ["repo-research", "ingest", str(tmp_path)])

    cli.main()

    result = json.loads(capsys.readouterr().out)
    assert database.replacements == []
    assert result["indexed_chunks"] == 3
    assert result["index_updated"] is False
    assert result["skipped_files"] == []


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
