.DEFAULT_GOAL := test

.PHONY: install format lint typecheck test docker-up docker-down ingest-self evaluate-retrieval api

install:
	uv sync --extra dev

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint:
	uv run ruff format --check src tests
	uv run ruff check src tests

typecheck:
	uv run mypy

test:
	uv run pytest

docker-up:
	docker compose up -d --wait qdrant

docker-down:
	docker compose down

ingest-self:
	uv run repo-research ingest .

evaluate-retrieval:
	uv run repo-research evaluate-retrieval

api:
	uv run uvicorn repo_research.api:app --reload
