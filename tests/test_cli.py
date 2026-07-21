"""Tests for the command-line boundary."""

from repo_research.cli import build_parser


def test_cli_parses_search_request() -> None:
    arguments = build_parser().parse_args(["search", "where is cost calculated?"])

    assert arguments.command == "search"
    assert arguments.query == "where is cost calculated?"
    assert arguments.limit == 5
