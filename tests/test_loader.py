"""Tests for local repository discovery and filtering."""

import subprocess
from pathlib import Path

import pytest

from repo_research.ingestion import discover_repository, materialize_repository_address


def test_discover_filters_ignored_binary_and_large_files(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "binary.py").write_bytes(b"\x00not source")
    (tmp_path / "large.md").write_text("x" * 20, encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "hidden.py").write_text("value = 3\n", encoding="utf-8")

    identity, files = discover_repository(tmp_path, max_file_size_bytes=10)

    assert identity.name == tmp_path.name
    assert [path.name for path in files] == ["keep.py"]


def test_materialize_repository_address_returns_local_path(tmp_path: Path) -> None:
    assert materialize_repository_address(str(tmp_path), tmp_path / "cache") == tmp_path


def test_materialize_repository_address_clones_public_github_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        target = Path(args[-1])
        (target / ".git").mkdir(parents=True)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    checkout = materialize_repository_address(
        "https://github.com/DataTalksClub/llm-zoomcamp.git",
        tmp_path / "cache",
    )

    assert checkout.name.startswith("DataTalksClub-llm-zoomcamp-")
    assert (checkout / ".git").is_dir()
    assert calls == [
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/DataTalksClub/llm-zoomcamp.git",
            str(checkout),
        ]
    ]


def test_materialize_repository_address_rejects_non_github_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only public github.com"):
        materialize_repository_address("https://example.com/owner/repo", tmp_path)
