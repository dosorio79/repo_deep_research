"""Validated runtime configuration for Repo Deep Research."""

import os
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from repo_research.models import RetrievalMode


def load_dotenv_environment(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries from .env into os.environ when missing."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_quotes(value.strip())


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


class Settings(BaseSettings):
    """Application settings loaded from environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RDR_",
        env_ignore_empty=True,
        extra="ignore",
        validate_by_name=True,
    )

    environment: str = "local"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "repo_chunks_v2"
    repository_root: Path = Path(".")
    max_file_size_bytes: int = Field(default=1_048_576, gt=0)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = Field(default=384, gt=0)
    embedding_batch_size: int = Field(default=16, gt=0)
    sparse_embedding_model: str = "Qdrant/bm25"
    retrieval_mode: RetrievalMode = RetrievalMode.DENSE
    openai_answer_model: str = Field(
        default="gpt-5-mini",
        validation_alias=AliasChoices(
            "openai_answer_model",
            "RDR_OPENAI_ANSWER_MODEL",
            "RDR_OPENAI_MODEL",
        ),
    )
    openai_judge_model: str = "gpt-5.1"
    retrieval_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "retrieval_limit",
            "RDR_RETRIEVAL_LIMIT",
            "RDR_RESEARCH_LIMIT",
        ),
    )
    answer_evaluation_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "answer_evaluation_limit",
            "RDR_ANSWER_EVALUATION_LIMIT",
            "RDR_ANSWER_EVAL_LIMIT",
        ),
    )
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    log_level: str = "INFO"

    @property
    def openai_model(self) -> str:
        """Backward-compatible name for the direct-RAG answer model."""
        return self.openai_answer_model

    @property
    def research_limit(self) -> int:
        """Backward-compatible name for the default research retrieval limit."""
        return self.retrieval_limit

    @property
    def answer_eval_limit(self) -> int:
        """Backward-compatible name for the answer-evaluation retrieval limit."""
        return self.answer_evaluation_limit

    @field_validator("qdrant_url")
    @classmethod
    def validate_qdrant_url(cls, value: str) -> str:
        """Require an HTTP endpoint so dependent clients receive a usable URL."""
        if not value.startswith(("http://", "https://")):
            message = "qdrant_url must start with http:// or https://"
            raise ValueError(message)
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize a common environment override while retaining validation."""
        normalized = value.upper()
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in valid_levels:
            message = f"log_level must be one of {sorted(valid_levels)}"
            raise ValueError(message)
        return normalized
