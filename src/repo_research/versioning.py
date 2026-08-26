"""Application version provenance helpers."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE_NAME = "repo-deep-research"
UNKNOWN_VERSION = "unknown"


@dataclass(frozen=True)
class AppVersionInfo:
    """Runtime application version metadata stored with persisted evidence."""

    app_version: str
    git_commit: str
    provenance: str = "exact"


@dataclass(frozen=True)
class ReleaseVersionWindow:
    """Conservative timestamp window used for legacy provenance backfill."""

    app_version: str
    start_at: datetime
    end_at: datetime
    git_commit: str = UNKNOWN_VERSION


LEGACY_RELEASE_WINDOWS: tuple[ReleaseVersionWindow, ...] = (
    ReleaseVersionWindow(
        app_version="0.5.9",
        start_at=datetime(2026, 8, 16, tzinfo=UTC),
        end_at=datetime(2026, 8, 21, tzinfo=UTC),
    ),
    ReleaseVersionWindow(
        app_version="0.6.0",
        start_at=datetime(2026, 8, 21, tzinfo=UTC),
        end_at=datetime(2026, 8, 23, tzinfo=UTC),
    ),
    ReleaseVersionWindow(
        app_version="0.6.1",
        start_at=datetime(2026, 8, 23, tzinfo=UTC),
        end_at=datetime(2026, 8, 25, tzinfo=UTC),
    ),
)


def current_app_version_info(repository_root: Path | None = None) -> AppVersionInfo:
    """Return best-effort exact version metadata for the running application."""
    try:
        app_version = version(PACKAGE_NAME)
    except PackageNotFoundError:
        app_version = UNKNOWN_VERSION
    git_commit = _current_git_commit(repository_root)
    return AppVersionInfo(
        app_version=app_version,
        git_commit=git_commit,
        provenance="exact" if app_version != UNKNOWN_VERSION else "unknown",
    )


def _current_git_commit(repository_root: Path | None) -> str:
    env_commit = os.getenv("RDR_APP_GIT_COMMIT")
    if env_commit and env_commit.strip():
        return env_commit.strip()
    cwd = repository_root or Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_VERSION
    commit = completed.stdout.strip()
    return commit or UNKNOWN_VERSION
