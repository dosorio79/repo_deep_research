.DEFAULT_GOAL := help

REPO_PATH ?= .
QUESTION ?= where is repository configuration validated?
LIMIT ?= 5
RETRIEVAL_MODE ?= dense
RAG_MODE ?= auto
DATASET ?= eval/development.json
API_URL ?= http://127.0.0.1:8000

.PHONY: help install format lint typecheck test validate docker-up docker-down ready ingest ingest-self evidence rag api-rag evaluate-retrieval evaluate-answers api

help:
	@printf '%s\n' 'Common workflow:'
	@printf '%s\n' '  make ready'
	@printf '%s\n' '  make evidence QUESTION="where is configuration validated?"'
	@printf '%s\n' '  make rag QUESTION="where is configuration validated?"'
	@printf '%s\n' '  make api       # run in one terminal'
	@printf '%s\n' '  make api-rag QUESTION="where is configuration validated?"'
	@printf '%s\n' ''
	@printf '%s\n' 'Other targets:'
	@printf '%s\n' '  make install | make validate | make docker-up | make docker-down'
	@printf '%s\n' '  make ingest REPO_PATH=/path/to/repo'
	@printf '%s\n' '  make evaluate-retrieval'
	@printf '%s\n' '  make evaluate-answers'
	@printf '%s\n' '  make api'

install:
	uv sync --dev

format:
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

lint:
	uv run ruff format --check src tests scripts
	uv run ruff check src tests scripts

typecheck:
	uv run mypy

test:
	uv run pytest

validate: lint typecheck test

docker-up:
	docker compose up -d --wait qdrant

docker-down:
	docker compose down

ready: install docker-up ingest-self

ingest:
	uv run repo-research ingest "$(REPO_PATH)"

ingest-self:
	uv run repo-research ingest .

evidence: docker-up
	uv run repo-research search "$(QUESTION)" --path "$(REPO_PATH)" --limit "$(LIMIT)" --mode "$(RETRIEVAL_MODE)"

rag: docker-up
	uv run repo-research rag "$(QUESTION)" --path "$(REPO_PATH)" --mode "$(RAG_MODE)" --limit "$(LIMIT)" --retrieval-mode "$(RETRIEVAL_MODE)"

api-rag: docker-up
	QUESTION="$(QUESTION)" REPO_PATH="$(REPO_PATH)" LIMIT="$(LIMIT)" RETRIEVAL_MODE="$(RETRIEVAL_MODE)" RAG_MODE="$(RAG_MODE)" API_URL="$(API_URL)" uv run python scripts/api_rag.py

evaluate-retrieval:
	uv run repo-research evaluate-retrieval --path "$(REPO_PATH)" --dataset "$(DATASET)" --output eval/results/retrieval-development.json --limit "$(LIMIT)"

evaluate-answers:
	uv run repo-research evaluate-answers --path "$(REPO_PATH)" --dataset "$(DATASET)" --output eval/results/answer-development.json --limit "$(LIMIT)" --retrieval-mode "$(RETRIEVAL_MODE)"

api:
	uv run uvicorn repo_research.api:app --reload
