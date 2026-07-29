# Repo Deep Research

Repo Deep Research is an evidence-grounded research tool for Python
repositories. It is the LLM Zoomcamp capstone: users can locate implementation
logic, understand module flow, and assess change impact using answers that cite
repository paths, symbols, and line ranges.

## Current status

M3 — Grounded direct RAG backend is implemented. The project supports dense,
sparse, and Qdrant RRF-hybrid retrieval, then uses a direct OpenAI Responses API
RAG baseline to produce structured answers with application-validated
citations. A minimal FastAPI backend exposes `/health` and `/research`.
PydanticAI agent loops, feedback, monitoring, and the React/Lovable frontend
remain deliberately deferred.

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
make evidence QUESTION="where is configuration validated?"
make rag QUESTION="where is configuration validated?" RESEARCH_MODE=locate
make evaluate-retrieval
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
| `make validate` | Run lint, typecheck, and tests. |
| `make docker-up` | Start the local Qdrant service. |
| `make docker-down` | Stop the local Qdrant service. |
| `make ready` | Install dependencies, start Qdrant, and ingest this repository. |
| `make ingest REPO_PATH=PATH` | Parse and index a local repository. |
| `make ingest-self` | Parse and index this repository. |
| `make evidence QUESTION="..."` | Start Qdrant and return repository evidence using dense retrieval by default. |
| `make rag QUESTION="..."` | Start Qdrant and return a grounded direct-RAG answer. |
| `make api-rag QUESTION="..."` | Start Qdrant and return a grounded answer through the local FastAPI `/research` endpoint. |
| `make evaluate-retrieval` | Evaluate dense, sparse, and hybrid retrieval on the development records. |
| `make evaluate-answers` | Run opt-in live answer judging with OpenAI. |
| `make api` | Run the minimal FastAPI backend on localhost. |

The main Make targets accept optional variables: `QUESTION`, `REPO_PATH`,
`LIMIT`, `RETRIEVAL_MODE`, `RESEARCH_MODE`, `DATASET`, and `API_URL`. Run
`make help` for examples.

## Configuration

Copy `.env.example` to `.env` for local overrides. All runtime settings use the
`RDR_` prefix and are validated by `repo_research.config.Settings`.

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
| `RDR_RETRIEVAL_MODE` | `dense` | Measured production retrieval default. |
| `RDR_OPENAI_MODEL` | `gpt-5-mini` | Default direct-RAG answer model. |
| `RDR_OPENAI_JUDGE_MODEL` | `gpt-5.1` | Default answer-evaluation judge model. |
| `RDR_RESEARCH_LIMIT` | `5` | Default retrieved evidence limit for research answers. |
| `RDR_ANSWER_EVAL_LIMIT` | `5` | Default retrieved evidence limit during answer evaluation. |
| `RDR_LOG_LEVEL` | `INFO` | Application log level. |

See [docs/setup.md](docs/setup.md), [docs/usage.md](docs/usage.md), and
[docs/architecture.md](docs/architecture.md) for the operational details. The
M1 implementation record is in
[docs/plans/m1-searchable-repository.md](docs/plans/m1-searchable-repository.md).
Reliability work completed before M2 is recorded in
[docs/plans/m1-reliability-hardening.md](docs/plans/m1-reliability-hardening.md).
The M2 implementation and evaluation procedure are in
[docs/plans/m2-evaluated-hybrid-retrieval.md](docs/plans/m2-evaluated-hybrid-retrieval.md)
and [docs/evaluation.md](docs/evaluation.md). The M3 implementation record is
in [docs/plans/m3-grounded-rag.md](docs/plans/m3-grounded-rag.md).

## M2 migration

M2 uses the new `repo_chunks_v2` default collection because its named
`dense`/`sparse` vector schema is incompatible with the M1 collection. Re-run
ingestion before searching or evaluating M2 modes.

## Roadmap

M4 adds bounded agentic research. Later milestones add feedback, monitoring,
and the product interface/operations stack.
The complete scope is in [docs/PRD.md](docs/PRD.md).
