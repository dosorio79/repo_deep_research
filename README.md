# Repo Deep Research

[![CI](https://github.com/dosorio79/repo_deep_research/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/dosorio79/repo_deep_research/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/dosorio79/repo_deep_research)](https://github.com/dosorio79/repo_deep_research/releases)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/downloads/release/python-3120/)

Repo Deep Research is an evidence-grounded research tool for Python
repositories. It is the LLM Zoomcamp capstone: users can locate implementation
logic, understand module flow, and assess change impact using answers that cite
repository paths, symbols, and line ranges.

## Current status

M3.6 — Frontend testing harness is implemented. The project supports dense,
sparse, and Qdrant RRF-hybrid retrieval, then uses a direct OpenAI Responses API
RAG baseline to produce structured answers with application-validated
citations. CLI and API RAG runs return an answer-plus-trace envelope with
repository identity, retrieval settings, latency, model usage, and estimated cost
metadata where pricing is known. A minimal FastAPI backend exposes `/health` and
`/rag`; browser CORS is opt-in through local configuration. The vendored React
TypeScript frontend under `frontend/` calls that `/rag` API and renders answer,
evidence, trace, cost telemetry, errors, and raw JSON. PydanticAI agent loops,
feedback persistence, and monitoring dashboards remain deliberately deferred.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose (only to run Qdrant)

## Quick start

```bash
cp .env.example .env
cp .env.local.example .env.local
make install
make test
make rag QUESTION="where is configuration validated?"
```

Qdrant is then available at `http://localhost:6333`; its local dashboard is at
`http://localhost:6333/dashboard`.

Stop the local service with `make docker-down`.

## Developer commands

| Command | Purpose |
|---|---|
| `make install` | Install locked runtime and development dependencies with uv. |
| `make format` | Apply Ruff formatting and safe lint fixes. |
| `make lint` | Check formatting and lint rules. |
| `make typecheck` | Run strict mypy checks. |
| `make test` | Run the unit test suite. |
| `make validate` / `make check` | Run lint, typecheck, and tests. |
| `make qdrant` / `make docker-up` | Start the local Qdrant service. |
| `make stop` / `make docker-down` | Stop the local Qdrant service. |
| `make ready` | Install dependencies, start Qdrant, and ingest this repository. |
| `make ingest` / `make ingest-self` | Parse and index this repository. |
| `make evidence QUESTION="..."` | Start Qdrant and return repository evidence using dense retrieval by default. |
| `make rag QUESTION="..."` | Ingest this repo if needed and return a grounded direct-RAG answer. |
| `make api-rag QUESTION="..."` | Start Qdrant and return answer-plus-trace JSON through the local FastAPI `/rag` endpoint. |
| `make evaluate-retrieval` | Evaluate dense, sparse, and hybrid retrieval on the development records. |
| `make evaluate-answers` | Run opt-in live answer judging with OpenAI. |
| `make api` | Run the minimal FastAPI backend on localhost. |
| `make app` | Run FastAPI and the M3.6 frontend together for local browser testing. |
| `make frontend-install` | Install the vendored frontend dependencies with npm. |
| `make frontend-dev` | Run the M3.6 frontend locally. |
| `make frontend-test` | Run frontend unit and contract tests. |
| `make frontend-typecheck` | Run TypeScript checks for the frontend. |
| `make frontend-build` | Build the frontend production bundle. |

The simplest user path is `make rag QUESTION="..."`. Use
`uv run repo-research ...` directly for path, mode, limit, dataset, and output
options.

## Configuration

Copy `.env.example` to `.env` for non-secret local defaults. Copy
`.env.local.example` to `.env.local` for secrets and machine-local overrides.
Both `.env` and `.env.local` are ignored; exported shell variables override both.
All runtime settings use the `RDR_` prefix and are validated by
`repo_research.config.Settings`.

| Variable | Default | Meaning |
|---|---|---|
| `RDR_ENVIRONMENT` | `local` | Runtime environment label. |
| `RDR_QDRANT_URL` | `http://localhost:6333` | Qdrant HTTP endpoint. |
| `RDR_QDRANT_COLLECTION` | `repo_chunks_v2` | Named dense/sparse vector collection for repository chunks. |
| `RDR_REPOSITORY_ROOT` | `.` | Default local repository path for CLI ingestion and search. |
| `RDR_MAX_FILE_SIZE_BYTES` | `1048576` | Maximum eligible source-file size during ingestion. |
| `RDR_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local FastEmbed/ONNX model. |
| `RDR_EMBEDDING_DIMENSION` | `384` | Required dense-vector dimension. |
| `RDR_EMBEDDING_BATCH_SIZE` | `16` | Bounded local ONNX indexing batch size. |
| `RDR_SPARSE_EMBEDDING_MODEL` | `Qdrant/bm25` | Local FastEmbed-compatible sparse encoder. |
| `RDR_RETRIEVAL_MODE` | `dense` | Measured production retrieval default; callers may still choose dense, sparse, or hybrid per request. |
| `RDR_RETRIEVAL_LIMIT` | `5` | Default retrieved evidence limit for direct-RAG answers. |
| `RDR_OPENAI_ANSWER_MODEL` | `gpt-5-mini` | Default direct-RAG answer model. |
| `RDR_OPENAI_JUDGE_MODEL` | `gpt-5.1` | Default answer-evaluation judge model. |
| `RDR_ANSWER_EVALUATION_LIMIT` | `5` | Default retrieved evidence limit during answer evaluation. |
| `RDR_CORS_ALLOWED_ORIGINS` | `[]` | JSON list of browser origins allowed to call FastAPI. `.env.example` opts in local frontend origins. |
| `RDR_LOG_LEVEL` | `INFO` | Application log level. |
| `OPENAI_API_KEY` | unset | OpenAI API key for live direct RAG and answer evaluation. Prefer `.env.local` or an exported shell variable. |

Legacy names `RDR_OPENAI_MODEL`, `RDR_RESEARCH_LIMIT`, and
`RDR_ANSWER_EVAL_LIMIT` remain accepted for existing local `.env` files, but new
configuration should use the grouped names above.

See [docs/setup.md](docs/setup.md), [docs/usage.md](docs/usage.md), and
[docs/architecture.md](docs/architecture.md) for the operational details. The
M1 implementation record is in
[docs/plans/m1-searchable-repository.md](docs/plans/m1-searchable-repository.md).
Reliability work completed before M2 is recorded in
[docs/plans/m1-reliability-hardening.md](docs/plans/m1-reliability-hardening.md).
The M2 implementation and evaluation procedure are in
[docs/plans/m2-evaluated-hybrid-retrieval.md](docs/plans/m2-evaluated-hybrid-retrieval.md)
and [docs/evaluation.md](docs/evaluation.md). The M3 implementation record is
in [docs/plans/m3-grounded-rag.md](docs/plans/m3-grounded-rag.md). The M3.6
frontend implementation is recorded in
[docs/plans/m3-6-frontend-harness.md](docs/plans/m3-6-frontend-harness.md).

## Branches and releases

`main` is production. `dev` is the integration branch and dev/preprod
environment. Feature work should branch from `dev`, merge back to `dev`, and
promote to `main` by pull request when ready for production.

Releases are `vMAJOR.MINOR.PATCH` tags cut from `main`; pushing a version tag
creates a GitHub Release. The first release for the M3 grounded direct-RAG state
is `v0.3.0`.

GitHub branch protection and repository environments are managed with Terraform
under [infra/github](infra/github/). The workflow details are recorded in
[docs/plans/release-branching.md](docs/plans/release-branching.md).

## M2 migration

M2 uses the new `repo_chunks_v2` default collection because its named
`dense`/`sparse` vector schema is incompatible with the M1 collection. Re-run
ingestion before searching or evaluating M2 modes.

## Roadmap

M4 adds bounded agentic research. M5 adds feedback persistence, Logfire,
dashboards, and the complete product operations stack.
The complete scope is in [docs/PRD.md](docs/PRD.md).
