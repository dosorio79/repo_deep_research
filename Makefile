.DEFAULT_GOAL := help
.SILENT:

QUESTION ?= where is repository configuration validated?
UV_CACHE_DIR ?= /tmp/repo_deep_research_uv_cache
UV := UV_CACHE_DIR=$(UV_CACHE_DIR) uv
RUN := $(UV) run
FRONTEND_NODE_VERSION := $(shell cat frontend/.nvmrc 2>/dev/null)
FRONTEND_NODE_BIN := $(HOME)/.nvm/versions/node/v$(FRONTEND_NODE_VERSION)/bin
FRONTEND_NPM := PATH=$(FRONTEND_NODE_BIN):$$PATH npm

.PHONY: help install format lint typecheck test coverage validate check test-all qdrant postgres stop ready ingest ingest-self evidence rag research api-rag evaluate-retrieval evaluate-answers api app frontend-install frontend-format frontend-lint frontend-typecheck frontend-test frontend-build frontend-dev docker-up docker-down

help:
	printf '%s\n' 'Common:'
	printf '%s\n' '  make ready       install deps, start services, ingest this repo'
	printf '%s\n' '  make check       backend lint, typecheck, and tests'
	printf '%s\n' '  make coverage    backend test coverage report'
	printf '%s\n' '  make test-all    backend check plus frontend test/typecheck/build'
	printf '%s\n' '  make evidence    retrieve evidence for QUESTION'
	printf '%s\n' '  make rag         direct RAG: ingest if needed, then answer QUESTION'
	printf '%s\n' '  make research    agentic RAG: ingest if needed, then answer QUESTION'
	printf '%s\n' '  make api         run FastAPI locally'
	printf '%s\n' '  make app         run FastAPI and the MVP frontend; ingest from the UI'
	printf '%s\n' '  make frontend-dev run the MVP frontend locally'
	printf '%s\n' '  make frontend-test | frontend-typecheck | frontend-build'
	printf '%s\n' ''
	printf '%s\n' 'Operations:'
	printf '%s\n' '  make qdrant                   start Qdrant only'
	printf '%s\n' '  make postgres                 start PostgreSQL only'
	printf '%s\n' '  make docker-up                start local services'
	printf '%s\n' '  make stop | make docker-down     stop local services'
	printf '%s\n' '  make ingest | make ingest-self   index this repository'
	printf '%s\n' '  make api-rag                     exercise FastAPI /rag'
	printf '%s\n' '  make evaluate-retrieval | make evaluate-answers'
	printf '%s\n' ''
	printf '%s\n' 'Example:'
	printf '%s\n' '  make rag QUESTION="where is configuration validated?"'
	printf '%s\n' '  make research QUESTION="which modules change for feedback?"'
	printf '%s\n' ''
	printf '%s\n' 'Use uv run repo-research ... directly for path, mode, limit, or dataset options.'

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

coverage:
	$(RUN) pytest --cov=repo_research --cov-report=term-missing

validate: lint typecheck test

check: validate

test-all: check frontend-test frontend-typecheck frontend-build

qdrant:
	docker compose up -d --wait qdrant

postgres:
	docker compose up -d --wait postgres

stop:
	docker compose down

docker-up: qdrant postgres

docker-down: stop

ready: install docker-up ingest

ingest:
	$(RUN) repo-research ingest .

ingest-self: ingest

evidence: qdrant
	$(RUN) repo-research search "$(QUESTION)"

rag:
	$(RUN) repo-research ask "$(QUESTION)"

research:
	$(RUN) repo-research research "$(QUESTION)"

api-rag: qdrant
	QUESTION="$(QUESTION)" $(RUN) python scripts/api_rag.py

evaluate-retrieval:
	$(RUN) repo-research evaluate-retrieval

evaluate-answers:
	$(RUN) repo-research evaluate-answers

api:
	$(RUN) uvicorn repo_research.api:app --reload

app: docker-up
	api_pid=""; \
	api_ready=""; \
	cleanup() { [ -n "$$api_pid" ] && kill "$$api_pid" 2>/dev/null || true; }; \
	trap cleanup INT TERM EXIT; \
	if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then \
		printf '%s\n' 'Starting API at http://127.0.0.1:8000'; \
		$(MAKE) api & \
		api_pid=$$!; \
	else \
		printf '%s\n' 'API already available at http://127.0.0.1:8000'; \
	fi; \
	for attempt in $$(seq 1 30); do \
		if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then \
			api_ready=1; \
			break; \
		fi; \
		sleep 1; \
	done; \
	if [ -z "$$api_ready" ]; then \
		printf '%s\n' 'API did not become available at http://127.0.0.1:8000/health' >&2; \
		exit 1; \
	fi; \
	printf '%s\n' 'Open frontend at http://127.0.0.1:5173'; \
	printf '%s\n' 'Frontend API base URL is /api, proxied to http://127.0.0.1:8000'; \
	$(MAKE) frontend-dev

frontend-install:
	cd frontend && $(FRONTEND_NPM) install

frontend-format:
	cd frontend && $(FRONTEND_NPM) run format

frontend-lint:
	cd frontend && $(FRONTEND_NPM) run lint

frontend-typecheck:
	cd frontend && $(FRONTEND_NPM) run typecheck

frontend-test:
	cd frontend && $(FRONTEND_NPM) test

frontend-build:
	cd frontend && $(FRONTEND_NPM) run build

frontend-dev:
	cd frontend && $(FRONTEND_NPM) run dev
