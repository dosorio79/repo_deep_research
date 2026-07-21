"""Tests for local repository discovery and filtering."""

from pathlib import Path

from repo_research.ingestion import discover_repository


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
