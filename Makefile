.DEFAULT_GOAL := help
.SILENT:

QUESTION ?= where is repository configuration validated?
UV_CACHE_DIR ?= /tmp/repo_deep_research_uv_cache
UV := UV_CACHE_DIR=$(UV_CACHE_DIR) uv
RUN := $(UV) run
FRONTEND_NODE_VERSION := $(shell cat frontend/.nvmrc 2>/dev/null)
FRONTEND_NODE_BIN := $(HOME)/.nvm/versions/node/v$(FRONTEND_NODE_VERSION)/bin
FRONTEND_NPM := PATH=$(FRONTEND_NODE_BIN):$$PATH npm

.PHONY: help install format lint typecheck test validate check qdrant stop ready ingest ingest-self evidence rag api-rag evaluate-retrieval evaluate-answers api app frontend-install frontend-lint frontend-typecheck frontend-test frontend-build frontend-dev docker-up docker-down

help:
	printf '%s\n' 'Common:'
	printf '%s\n' '  make ready       install deps, start Qdrant, ingest this repo'
	printf '%s\n' '  make check       lint, typecheck, and test'
	printf '%s\n' '  make evidence    retrieve evidence for QUESTION'
	printf '%s\n' '  make rag         ingest if needed, then answer QUESTION'
	printf '%s\n' '  make api         run FastAPI locally'
	printf '%s\n' '  make app         run FastAPI and the M3.6 frontend together'
	printf '%s\n' '  make frontend-dev run the M3.6 frontend locally'
	printf '%s\n' '  make frontend-test | frontend-build'
	printf '%s\n' ''
	printf '%s\n' 'Operations:'
	printf '%s\n' '  make qdrant | make stop | make ingest | make api-rag'
	printf '%s\n' '  make evaluate-retrieval | make evaluate-answers'
	printf '%s\n' ''
	printf '%s\n' 'Example:'
	printf '%s\n' '  make rag QUESTION="where is configuration validated?"'
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

validate: lint typecheck test

check: validate

qdrant:
	docker compose up -d --wait qdrant

stop:
	docker compose down

docker-up: qdrant

docker-down: stop

ready: install qdrant ingest

ingest:
	$(RUN) repo-research ingest .

ingest-self: ingest

evidence: qdrant
	$(RUN) repo-research search "$(QUESTION)"

rag:
	$(RUN) repo-research ask "$(QUESTION)"

api-rag: qdrant
	QUESTION="$(QUESTION)" $(RUN) python scripts/api_rag.py

evaluate-retrieval:
	$(RUN) repo-research evaluate-retrieval

evaluate-answers:
	$(RUN) repo-research evaluate-answers

api:
	$(RUN) uvicorn repo_research.api:app --reload

app: qdrant ingest
	api_pid=""; \
	cleanup() { [ -n "$$api_pid" ] && kill "$$api_pid" 2>/dev/null || true; }; \
	trap cleanup INT TERM EXIT; \
	if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then \
		$(MAKE) api & \
		api_pid=$$!; \
	fi; \
	for attempt in $$(seq 1 30); do \
		curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; \
		sleep 1; \
	done; \
	$(MAKE) frontend-dev

frontend-install:
	cd frontend && $(FRONTEND_NPM) install

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
