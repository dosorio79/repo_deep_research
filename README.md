# Repo Deep Research

Repo Deep Research will be an evidence-grounded research tool for Python
repositories. It is the LLM Zoomcamp capstone: users will be able to locate
implementation logic, understand module flow, and assess change impact using
answers that cite repository paths, symbols, and line ranges.

## Current status

M1.1 — Searchable repository is complete and safe to retry. The project
discovers local Python repositories, creates evidence-rich
Python/Markdown/configuration chunks, indexes local ONNX dense vectors in
Qdrant, and exposes CLI ingestion/search with skipped-file diagnostics. Sparse
or hybrid retrieval, answer generation, agents, API/UI, feedback, and
monitoring remain deliberately deferred.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose (only to run Qdrant)

## Quick start

```bash
cp .env.example .env
make install
make test
make docker-up
make ingest-self
uv run repo-research search "where is configuration validated?"
```

Qdrant is then available at `http://localhost:6333`; its local dashboard is at
`http://localhost:6333/dashboard`.

Stop the local service with `make docker-down`.

## Developer commands

| Command | Purpose |
|---|---|
| `make install` | Install locked development dependencies with uv. |
| `make format` | Apply Ruff formatting and safe lint fixes. |
| `make lint` | Check formatting and lint rules. |
| `make typecheck` | Run strict mypy checks. |
| `make test` | Run the unit test suite. |
| `make docker-up` | Start the local Qdrant service. |
| `make docker-down` | Stop the local Qdrant service. |
| `make ingest-self` | Parse and densely index this repository. |
| `uv run repo-research ingest PATH` | Parse and index a local repository. |
| `uv run repo-research search QUERY` | Return dense evidence for the configured repository. |

## Configuration

Copy `.env.example` to `.env` for local overrides. All runtime settings use the
`RDR_` prefix and are validated by `repo_research.config.Settings`.

| Variable | Default | Meaning |
|---|---|---|
| `RDR_ENVIRONMENT` | `local` | Runtime environment label. |
| `RDR_QDRANT_URL` | `http://localhost:6333` | Qdrant HTTP endpoint. |
| `RDR_QDRANT_COLLECTION` | `repo_chunks` | Future collection name for repository chunks. |
| `RDR_REPOSITORY_ROOT` | `.` | Default local repository path for CLI ingestion and search. |
| `RDR_MAX_FILE_SIZE_BYTES` | `1048576` | Maximum eligible source-file size during ingestion. |
| `RDR_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local FastEmbed/ONNX model. |
| `RDR_EMBEDDING_DIMENSION` | `384` | Required dense-vector dimension. |
| `RDR_EMBEDDING_BATCH_SIZE` | `16` | Bounded local ONNX indexing batch size. |
| `RDR_LOG_LEVEL` | `INFO` | Application log level. |

See [docs/setup.md](docs/setup.md), [docs/usage.md](docs/usage.md), and
[docs/architecture.md](docs/architecture.md) for the operational details. The
M1 implementation record is in
[docs/plans/m1-searchable-repository.md](docs/plans/m1-searchable-repository.md).
Reliability work completed before M2 is recorded in
[docs/plans/m1-reliability-hardening.md](docs/plans/m1-reliability-hardening.md).

## Roadmap

M2 adds sparse/hybrid retrieval and evaluation. Later milestones add grounded
answers, bounded agentic research, and the product interface/operations stack.
The complete scope is in [docs/PRD.md](docs/PRD.md).
