"""Validated runtime configuration for Repo Deep Research."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from repo_research.models import RetrievalMode


class Settings(BaseSettings):
    """Application settings loaded from environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RDR_",
        env_ignore_empty=True,
        extra="ignore",
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
    log_level: str = "INFO"

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
