.DEFAULT_GOAL := help
.SILENT:

QUESTION ?= where is repository configuration validated?
UV_CACHE_DIR ?= /tmp/repo_deep_research_uv_cache
UV := UV_CACHE_DIR=$(UV_CACHE_DIR) uv
RUN := $(UV) run
FRONTEND_NODE_VERSION := $(shell cat frontend/.nvmrc 2>/dev/null)
FRONTEND_NODE_BIN := $(HOME)/.nvm/versions/node/v$(FRONTEND_NODE_VERSION)/bin
FRONTEND_NPM := PATH=$(FRONTEND_NODE_BIN):$$PATH npm

.PHONY: help install format lint typecheck test check test-all services-up services-down stack-start stack-rebuild stack-up stack-stop stack-down ingest graph-summary rag research evaluate-retrieval evaluate-answers evaluate-relationship-graph export-openapi api app

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------

help:
	printf '%s\n' 'Repo Deep Research commands:'
	printf '%s\n' ''
	printf '%s\n' 'Quality'
	printf '%s\n' '  make install                install Python dependencies'
	printf '%s\n' '  make format                 format and fix backend code'
	printf '%s\n' '  make lint                   check backend formatting and lint'
	printf '%s\n' '  make typecheck              run mypy'
	printf '%s\n' '  make test                   run backend tests'
	printf '%s\n' '  make check                  backend lint, typecheck, and tests'
	printf '%s\n' '  make test-all               backend checks plus frontend lint/tests/typecheck/build'
	printf '%s\n' ''
	printf '%s\n' 'Services and stack'
	printf '%s\n' '  make services-up            start Qdrant and PostgreSQL'
	printf '%s\n' '  make services-down          stop local services'
	printf '%s\n' '  make stack-up               create and start full stack'
	printf '%s\n' '  make stack-down             stop and remove full stack'
	printf '%s\n' '  make stack-start            start existing full stack containers'
	printf '%s\n' '  make stack-stop             stop existing full stack containers'
	printf '%s\n' '  make stack-rebuild          rebuild images and start full stack'
	printf '%s\n' ''
	printf '%s\n' 'Repository workflows'
	printf '%s\n' '  make ingest                 index this repository'
	printf '%s\n' '  make graph-summary          print current repository graph summary'
	printf '%s\n' '  make rag QUESTION="..."     run direct RAG'
	printf '%s\n' '  make research QUESTION="..." run bounded agentic research'
	printf '%s\n' ''
	printf '%s\n' 'Evaluation'
	printf '%s\n' '  make evaluate-retrieval     compare retrieval modes'
	printf '%s\n' '  make evaluate-answers       run answer evaluation'
	printf '%s\n' '  make evaluate-relationship-graph run graph readiness evaluation'
	printf '%s\n' '  make export-openapi         refresh docs/api/openapi.json'
	printf '%s\n' ''
	printf '%s\n' 'Local app'
	printf '%s\n' '  make api                    run FastAPI locally'
	printf '%s\n' '  make app                    run API and frontend locally'
	printf '%s\n' ''
	printf '%s\n' 'Frontend-only commands: cd frontend && npm run lint | npm test | npm run typecheck | npm run build'
	printf '%s\n' 'Use uv run repo-research ... directly for path, mode, limit, dataset, and output options.'

# -----------------------------------------------------------------------------
# Quality
# -----------------------------------------------------------------------------

install:
	$(UV) sync --dev

format:
	$(RUN) ruff format src tests scripts
	$(RUN) ruff check --fix src tests scripts

lint:
	$(RUN) ruff format --check src tests scripts
	$(RUN) ruff check src tests scripts

typecheck:
	$(RUN) mypy

test:
	$(RUN) pytest

check: lint typecheck test

test-all: check
	cd frontend && $(FRONTEND_NPM) run lint
	cd frontend && $(FRONTEND_NPM) test
	cd frontend && $(FRONTEND_NPM) run typecheck
	cd frontend && $(FRONTEND_NPM) run build

# -----------------------------------------------------------------------------
# Services and stack
# -----------------------------------------------------------------------------

services-up:
	docker compose up -d --wait qdrant postgres

services-down:
	docker compose down

stack-start:
	docker compose start

stack-rebuild:
	docker compose up --build -d --wait

stack-up:
	docker compose up -d --wait

stack-stop:
	docker compose stop

stack-down:
	docker compose down

# -----------------------------------------------------------------------------
# Repository workflows
# -----------------------------------------------------------------------------

ingest:
	$(RUN) repo-research ingest .

graph-summary:
	$(RUN) repo-research graph-summary --path .

rag:
	$(RUN) repo-research ask "$(QUESTION)"

research:
	$(RUN) repo-research research "$(QUESTION)"

# -----------------------------------------------------------------------------
# Evaluation
# -----------------------------------------------------------------------------

evaluate-retrieval:
	$(RUN) repo-research evaluate-retrieval

evaluate-answers:
	$(RUN) repo-research evaluate-answers

evaluate-relationship-graph:
	$(RUN) python scripts/evaluate_relationship_graph.py $(if $(RUN_ANSWERS),--run-answers)

export-openapi:
	$(RUN) repo-research export-openapi

# -----------------------------------------------------------------------------
# Local app
# -----------------------------------------------------------------------------

api:
	$(RUN) uvicorn repo_research.api:app --reload

app: services-up
	UV_CACHE_DIR=$(UV_CACHE_DIR) PATH=$(FRONTEND_NODE_BIN):$$PATH bash scripts/app.sh
