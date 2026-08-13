# Repo Deep Research

[![CI](https://github.com/dosorio79/repo_deep_research/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/dosorio79/repo_deep_research/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/dosorio79/repo_deep_research)](https://github.com/dosorio79/repo_deep_research/releases)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/downloads/release/python-3120/)

Repo Deep Research is an evidence-grounded research tool for Python
repositories. It indexes source code and project documentation, retrieves
repository evidence, and answers questions about implementation locations,
module flow, and likely change impact with cited paths, symbols, and line
ranges.

The app provides a CLI, FastAPI backend, React frontend, local Qdrant vector
search, PostgreSQL-backed monitoring and feedback, direct RAG, bounded agentic
research, and opt-in answer evaluation.

## Release Status

The latest release is `v0.5.7`. The next planned delivery is
`v0.5.8 Local Alpha`: a local-first, bring-your-own-key release for technical
users who can run Docker Compose and provide their own OpenAI API key.

Cloud deployment is intentionally out of scope for the Local Alpha. The stack
includes a frontend, API, Qdrant, PostgreSQL, local repository ingestion, and
user-provided model credentials, which is too much moving infrastructure for a
free hosted demo target such as Render.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Node.js matching `frontend/.nvmrc` for frontend development

## Quick Start

```bash
cp .env.example .env
cp .env.local.example .env.local
make install
make services-up
make ingest
make rag QUESTION="where is configuration validated?"
```

Set `OPENAI_API_KEY` in `.env.local` before running live RAG, agentic research,
or answer evaluation.

For the full Local Alpha path, use the container stack:

```bash
make stack-up
```

Then open `http://localhost:3000`, ingest a repository, ask a direct or agentic
question, submit feedback, and inspect monitoring and evaluation dashboards.

## Main Commands

| Command | Purpose |
|---|---|
| `make install` | Install Python dependencies with uv. |
| `make format` | Apply Ruff formatting and safe lint fixes. |
| `make lint` | Check formatting and lint rules. |
| `make typecheck` | Run mypy. |
| `make test` | Run backend tests. |
| `make check` | Run backend lint, typecheck, and tests. |
| `make test-all` | Run backend checks plus frontend tests, typecheck, and build. |
| `make services-up` | Start Qdrant and PostgreSQL. |
| `make services-down` | Stop local services. |
| `make stack-up` | Build and start API, frontend, Qdrant, and PostgreSQL. |
| `make stack-down` | Stop the full stack. |
| `make ingest` | Index this repository. |
| `make rag QUESTION="..."` | Run direct RAG against the indexed repository. |
| `make research QUESTION="..."` | Run bounded agentic repository research. |
| `make evaluate-retrieval` | Compare dense, sparse, and hybrid retrieval. |
| `make evaluate-answers` | Run opt-in answer evaluation. |
| `make api` | Run FastAPI locally. |
| `make app` | Run the API and Vite frontend locally. |

Frontend-only workflows use npm directly:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

Use `uv run repo-research ...` directly for path, mode, limit, dataset, and
output options.

## Local App Flow

Run the production-like container stack:

```bash
make stack-up
```

Open `http://localhost:3000`, ingest a repository, ask a direct or agentic
question, submit feedback, inspect persisted monitoring at
`http://localhost:3000/monitoring`, and review persisted answer evaluations at
`http://localhost:3000/evaluations`.

For local development with FastAPI reload and the Vite dev server:

```bash
make app
```

The frontend runs at `http://127.0.0.1:5173` and proxies `/api/*` to
`http://127.0.0.1:8000`.

Stop services with:

```bash
make services-down
# or, for the full container stack:
make stack-down
```

## Configuration

Copy `.env.example` to `.env` for stable local defaults. Copy
`.env.local.example` to `.env.local` for secrets and machine-local overrides.
Exported shell variables take precedence.

Important settings:

| Variable | Meaning |
|---|---|
| `RDR_QDRANT_URL` | Qdrant HTTP endpoint. |
| `RDR_QDRANT_COLLECTION` | Qdrant collection for repository chunks. |
| `RDR_REPOSITORY_ROOT` | Default repository path for CLI commands. |
| `RDR_RETRIEVAL_MODE` | Default retrieval mode: `dense`, `sparse`, or `hybrid`. |
| `RDR_RETRIEVAL_LIMIT` | Default retrieved evidence limit. |
| `RDR_OPENAI_ANSWER_MODEL` | Model used for direct RAG and agentic answers. |
| `RDR_OPENAI_JUDGE_MODEL` | Model used for answer evaluation. |
| `RDR_POSTGRES_DSN` | PostgreSQL DSN for monitoring, feedback, and evaluation data. |
| `RDR_TELEMETRY_ENABLED` | Enables persisted recording when PostgreSQL is configured. |
| `RDR_CORS_ALLOWED_ORIGINS` | Browser origins allowed to call FastAPI. |
| `OPENAI_API_KEY` | Required for live answer generation and judging. |

Legacy names `RDR_OPENAI_MODEL`, `RDR_RESEARCH_LIMIT`, and
`RDR_ANSWER_EVAL_LIMIT` remain accepted.

## More Documentation

- [Setup](docs/setup.md)
- [Usage](docs/usage.md)
- [Architecture](docs/architecture.md) including the Local Alpha stack diagram
- [Evaluation](docs/evaluation.md)
- [Implementation history](docs/plans/)

## Branches and Releases

`main` is production. `dev` is the integration branch. Feature branches start
from `dev`, merge back to `dev`, and promote to `main` when ready.

Releases are `vMAJOR.MINOR.PATCH` tags cut from `main`. The current user-ready
MVP stack is released as `v0.5.7`.

## Local Alpha Scope

`v0.5.8 Local Alpha` is planned as the first user-ready alpha. It should prove
that a user can run the product locally, bring their own model key, ingest a
repository, ask grounded repository questions, and inspect monitoring and
evaluation evidence.

Included:

- Local Docker Compose stack for frontend, API, Qdrant, and PostgreSQL.
- BYOK OpenAI configuration through `.env.local`.
- Direct RAG and bounded agentic research paths.
- Persisted monitoring, feedback, answer snapshots, and evaluation dashboards.
- User-facing screenshots, examples, runbook, and known limitations.

Not included:

- Hosted public demo.
- Free Render deployment.
- Multi-tenant authentication.
- Managed cloud persistence.
- Automatic code changes or pull requests.
