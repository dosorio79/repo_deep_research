"""Tests for the runtime configuration boundary."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from repo_research.config import Settings, load_dotenv_environment
from repo_research.models import RetrievalMode


def test_settings_use_local_defaults() -> None:
    settings = Settings()

    assert settings.environment == "local"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.repository_root == Path(".")
    assert settings.max_file_size_bytes == 1_048_576
    assert settings.embedding_batch_size == 16
    assert settings.qdrant_collection == "repo_chunks_v2"
    assert settings.sparse_embedding_model == "Qdrant/bm25"
    assert settings.retrieval_mode is RetrievalMode.DENSE
    assert settings.openai_model == "gpt-5-mini"
    assert settings.openai_judge_model == "gpt-5.1"
    assert settings.research_limit == 5
    assert settings.answer_eval_limit == 5


def test_settings_read_prefixed_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RDR_QDRANT_URL", "https://qdrant.example.test/")
    monkeypatch.setenv("RDR_LOG_LEVEL", "debug")

    settings = Settings()

    assert settings.qdrant_url == "https://qdrant.example.test"
    assert settings.log_level == "DEBUG"


def test_settings_reject_invalid_qdrant_url() -> None:
    with pytest.raises(ValidationError, match="qdrant_url"):
        Settings(qdrant_url="localhost:6333")


def test_settings_reject_non_positive_file_size() -> None:
    with pytest.raises(ValidationError, match="max_file_size_bytes"):
        Settings(max_file_size_bytes=0)


def test_load_dotenv_environment_loads_unprefixed_openai_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'OPENAI_API_KEY="test-key"\nRDR_QDRANT_URL=http://example.test\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RDR_QDRANT_URL", "http://already-set.test")

    load_dotenv_environment(env_file)

    assert os.environ["OPENAI_API_KEY"] == "test-key"
    assert os.environ["RDR_QDRANT_URL"] == "http://already-set.test"
