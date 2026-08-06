"""Tests for the runtime configuration boundary."""

import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from repo_research.config import Settings, load_dotenv_environment
from repo_research.models import ResearchBudget, RetrievalMode


def make_settings(**kwargs: Any) -> Settings:
    """Build settings with pydantic-settings private test overrides."""
    return Settings(**kwargs)


@pytest.fixture(autouse=True)
def clear_rdr_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep config tests independent from app-level dotenv loading."""
    for key in tuple(os.environ):
        if key.startswith("RDR_"):
            monkeypatch.delenv(key, raising=False)


def test_settings_use_local_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = make_settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.repository_root == Path(".")
    assert settings.max_file_size_bytes == 1_048_576
    assert settings.embedding_batch_size == 16
    assert settings.qdrant_collection == "repo_chunks_v2"
    assert settings.sparse_embedding_model == "Qdrant/bm25"
    assert settings.retrieval_mode is RetrievalMode.DENSE
    assert settings.openai_answer_model == "gpt-5-mini"
    assert settings.openai_model == "gpt-5-mini"
    assert settings.openai_judge_model == "gpt-5.1"
    assert settings.retrieval_limit == 5
    assert settings.research_limit == 5
    assert settings.answer_evaluation_limit == 5
    assert settings.answer_eval_limit == 5
    assert settings.research_max_searches == 3
    assert settings.research_max_file_reads == 5
    assert settings.research_max_total_tool_calls == 8
    assert settings.research_budget == ResearchBudget(
        max_searches=3,
        max_file_reads=5,
        max_total_tool_calls=8,
    )
    assert settings.cors_allowed_origins == []


def test_settings_read_prefixed_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RDR_QDRANT_URL", "https://qdrant.example.test/")
    monkeypatch.setenv("RDR_LOG_LEVEL", "debug")

    settings = make_settings(_env_file=None)

    assert settings.qdrant_url == "https://qdrant.example.test"
    assert settings.log_level == "DEBUG"


def test_settings_read_env_local_after_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "RDR_QDRANT_URL=http://env.example.test\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "RDR_QDRANT_URL=http://local.example.test\n",
        encoding="utf-8",
    )

    settings = make_settings(_env_file=(tmp_path / ".env", tmp_path / ".env.local"))

    assert settings.qdrant_url == "http://local.example.test"


def test_settings_read_grouped_openai_and_limit_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RDR_OPENAI_ANSWER_MODEL", "answer-model")
    monkeypatch.setenv("RDR_RETRIEVAL_LIMIT", "7")
    monkeypatch.setenv("RDR_ANSWER_EVALUATION_LIMIT", "3")
    monkeypatch.setenv("RDR_RESEARCH_MAX_SEARCHES", "2")
    monkeypatch.setenv("RDR_RESEARCH_MAX_FILE_READS", "4")
    monkeypatch.setenv("RDR_RESEARCH_MAX_TOTAL_TOOL_CALLS", "6")

    settings = make_settings(_env_file=None)

    assert settings.openai_answer_model == "answer-model"
    assert settings.retrieval_limit == 7
    assert settings.answer_evaluation_limit == 3
    assert settings.research_max_searches == 2
    assert settings.research_max_file_reads == 4
    assert settings.research_max_total_tool_calls == 6
    assert settings.research_budget == ResearchBudget(
        max_searches=2,
        max_file_reads=4,
        max_total_tool_calls=6,
    )


def test_settings_reject_research_budget_that_exceeds_total_calls() -> None:
    with pytest.raises(ValidationError, match="max_searches"):
        make_settings(
            _env_file=None,
            research_max_searches=4,
            research_max_file_reads=2,
            research_max_total_tool_calls=3,
        )

    with pytest.raises(ValidationError, match="max_file_reads"):
        make_settings(
            _env_file=None,
            research_max_searches=2,
            research_max_file_reads=4,
            research_max_total_tool_calls=3,
        )


def test_settings_parses_json_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "RDR_CORS_ALLOWED_ORIGINS",
        '["http://localhost:5173", "http://127.0.0.1:5173"]',
    )

    settings = make_settings(_env_file=None)

    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_settings_keep_legacy_openai_and_limit_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RDR_OPENAI_MODEL", "legacy-answer-model")
    monkeypatch.setenv("RDR_RESEARCH_LIMIT", "6")
    monkeypatch.setenv("RDR_ANSWER_EVAL_LIMIT", "4")

    settings = make_settings(_env_file=None)

    assert settings.openai_answer_model == "legacy-answer-model"
    assert settings.retrieval_limit == 6
    assert settings.answer_evaluation_limit == 4


def test_settings_accept_field_name_overrides() -> None:
    settings = make_settings(
        _env_file=None,
        openai_answer_model="custom-answer-model",
        retrieval_limit=2,
        answer_evaluation_limit=3,
        cors_allowed_origins=["http://localhost:8080"],
    )

    assert settings.openai_answer_model == "custom-answer-model"
    assert settings.retrieval_limit == 2
    assert settings.answer_evaluation_limit == 3
    assert settings.cors_allowed_origins == ["http://localhost:8080"]


def test_settings_reject_invalid_qdrant_url() -> None:
    with pytest.raises(ValidationError, match="qdrant_url"):
        make_settings(_env_file=None, qdrant_url="localhost:6333")


def test_settings_reject_non_positive_file_size() -> None:
    with pytest.raises(ValidationError, match="max_file_size_bytes"):
        make_settings(_env_file=None, max_file_size_bytes=0)


def test_load_dotenv_environment_loads_unprefixed_openai_key_and_local_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=\nRDR_QDRANT_URL=http://example.test\n",
        encoding="utf-8",
    )
    local_env_file = tmp_path / ".env.local"
    local_env_file.write_text(
        'OPENAI_API_KEY="local-test-key"\nRDR_QDRANT_URL=http://local.test\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RDR_QDRANT_URL", "http://already-set.test")

    load_dotenv_environment((env_file, local_env_file))

    assert os.environ["OPENAI_API_KEY"] == "local-test-key"
    assert os.environ["RDR_QDRANT_URL"] == "http://already-set.test"
