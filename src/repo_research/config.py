"""Validated runtime configuration for Repo Deep Research."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from repo_research.models import ResearchBudget, RetrievalMode

DEFAULT_DOTENV_PATHS = (Path(".env"), Path(".env.local"))


def load_dotenv_environment(
    paths: Path | Iterable[Path] = DEFAULT_DOTENV_PATHS,
    *,
    keys: Iterable[str] | None = None,
) -> None:
    """Load local KEY=VALUE files while preserving exported environment values."""
    dotenv_paths = (paths,) if isinstance(paths, Path) else tuple(paths)
    allowed_keys = set(keys) if keys is not None else None
    protected_keys = {key for key, value in os.environ.items() if value != ""}
    for path in dotenv_paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if allowed_keys is not None and key not in allowed_keys:
                continue
            parsed_value = _strip_env_quotes(value.strip())
            if not key or key in protected_keys or parsed_value == "":
                continue
            os.environ[key] = parsed_value


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


class Settings(BaseSettings):
    """Application settings loaded from environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_prefix="RDR_",
        env_ignore_empty=True,
        extra="ignore",
        validate_by_name=True,
    )

    environment: str = "local"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "repo_chunks_v2"
    repository_root: Path = Path(".")
    repository_cache_dir: Path = Path(".repo_research_cache/repositories")
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
    research_max_searches: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "research_max_searches",
            "RDR_RESEARCH_MAX_SEARCHES",
        ),
    )
    research_max_file_reads: int = Field(
        default=6,
        ge=0,
        le=20,
        validation_alias=AliasChoices(
            "research_max_file_reads",
            "RDR_RESEARCH_MAX_FILE_READS",
        ),
    )
    research_max_total_tool_calls: int = Field(
        default=12,
        ge=1,
        le=40,
        validation_alias=AliasChoices(
            "research_max_total_tool_calls",
            "RDR_RESEARCH_MAX_TOTAL_TOOL_CALLS",
        ),
    )
    cors_allowed_origins: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "cors_allowed_origins",
            "RDR_CORS_ALLOWED_ORIGINS",
        ),
    )
    postgres_dsn: str | None = Field(
        default=None,
        validation_alias=AliasChoices("postgres_dsn", "RDR_POSTGRES_DSN"),
    )
    telemetry_enabled: bool = True
    logfire_enabled: bool = False
    logfire_send_to_logfire: bool = False
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

    @property
    def research_budget(self) -> ResearchBudget:
        """Return the validated default budget for an agentic research run."""
        return ResearchBudget(
            max_searches=self.research_max_searches,
            max_file_reads=self.research_max_file_reads,
            max_total_tool_calls=self.research_max_total_tool_calls,
        )

    @model_validator(mode="after")
    def validate_research_budget(self) -> Self:
        """Reject default tool bounds that cannot form a valid research budget."""
        _ = self.research_budget
        return self

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
