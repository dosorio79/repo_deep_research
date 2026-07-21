"""Tests for the runtime configuration boundary."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from repo_research.config import Settings


def test_settings_use_local_defaults() -> None:
    settings = Settings()

    assert settings.environment == "local"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.repository_root == Path(".")
    assert settings.max_file_size_bytes == 1_048_576
    assert settings.embedding_batch_size == 16


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
