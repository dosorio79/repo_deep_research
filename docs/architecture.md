# Architecture

## Working layers

```text
Makefile
  Thin developer shortcuts: ready, evidence, rag, research, api, app, frontend-*.

Entry points
  repo-research CLI for local commands.
  FastAPI for the browser frontend and HTTP contract tests.
  React TypeScript frontend under frontend/ for research, feedback, and monitoring.

Runtime composition
  runtime.py creates shared database, model, direct-RAG, research-agent, and
  recording-store dependencies.

Service layer
  rag.py        runs direct RAG, citation validation, and answer evaluation.
  research.py   runs bounded agentic research with PydanticAI and typed tools.

Retrieval and storage
  qdrant_store.py  owns FastEmbed, Qdrant payloads, and dense/sparse/hybrid search.

Persistence
  recording_store.py  persists run telemetry and feedback in PostgreSQL.

Ingestion
  ingestion.py  discovers files, records Git identity, filters, and parses.

Observability
  monitoring.py   opt-in Logfire instrumentation for FastAPI and PydanticAI.
  telemetry.py    application telemetry helpers.
  pricing.py      OpenAI cost estimation separate from answer generation.
```

Both `make rag` and `make api-rag` reach the same `DirectRagService` through the
same runtime composition module. The difference is the entry point: `rag` calls
the CLI directly, while `api-rag` posts to FastAPI `/rag` and exercises the
HTTP contract that the frontend uses.

`make research` and `POST /research` reach the same `BoundedResearchService`
with configurable tool-call budgets for searches, file reads, and total calls.

## API surface

```text
GET  /            API index with endpoint listing
GET  /health      Qdrant dependency health
POST /repositories/ingest   Parse and index a repository
POST /rag         Direct RAG answer with trace metadata
POST /research    Bounded agentic research with trace metadata
POST /feedback    Persist useful/not-useful feedback linked by session_id
GET  /monitoring/summary    Aggregate dashboard data from PostgreSQL
```

## Data flow

```text
Local repository path or GitHub URL
        |
        v
ingestion.py -- filters, Git identity, and parsing
        |
        v
qdrant_store.py -- FastEmbed (local ONNX), current chunk payloads, vector search
        |
        v
rag.py / research.py -- direct RAG or bounded agentic research
        |
        v
recording_store.py -- persist run trace and feedback in PostgreSQL
        |
        v
repo-research CLI / FastAPI -- JSON evidence and grounded answers
        |
        v
frontend/ -- browser research UI, feedback, and monitoring dashboard
```

`ParsedChunk` is the boundary between parsing and storage. It carries the
repository and commit identity, path, symbol, parent symbol, line range,
content, contextual metadata, and deterministic content/point IDs. Qdrant
persists that complete payload, allowing the CLI to return evidence rather than
only text snippets.

`RepositoryDatabase` stages a replacement by validating dense and sparse
embeddings and upserting named `dense`/`sparse` vectors before deleting stale
point IDs. This retains the previous searchable index if validation or upsert
fails. Search is scoped to both repository and commit identity. Dense and sparse
queries return the same typed shape; hybrid search uses Qdrant Reciprocal Rank
Fusion over bounded candidates. Incremental commit comparison, rewriting, and
reranking remain deferred.

`ingestion.py` reports decoding, filesystem, and syntax failures for individual
eligible files without discarding successfully parsed chunks. The CLI emits
those diagnostics alongside the repository identity and indexed-chunk count.

`evaluation.py` loads versioned JSON ground truth, runs every baseline retrieval
mode, and writes deterministic file- and symbol-level metric reports. It uses a
small search protocol, so metric tests require neither a model nor Qdrant.

`rag.py` adds the direct-RAG layer. It preserves the result order returned by the
selected retrieval mode, assigns opaque evidence IDs to retrieved chunks, asks
the answer model to cite only those IDs, then maps valid IDs back to canonical
paths, symbols, and line ranges from storage. Unknown citations or empty
retrieval results return explicit insufficient-evidence answers. RAG runs return
`RagRunResult`, keeping model-authored answer content under `answer` and
application-owned telemetry under `trace`. The trace records repository identity,
retrieval settings, retrieved chunk counts, latency, model usage, estimated cost
where pricing is known, and direct-RAG tool-call count.

`research.py` adds the bounded agentic research layer using PydanticAI. The
`BoundedResearchService` enforces configurable limits on search calls, file
reads, and total tool calls. Tools include `search_repository`, `read_chunk`,
`read_file`, and `find_symbol`. The agent produces structured change-impact
output grounded in retrieved or read repository evidence. When the tool budget
is reached with collected evidence, a deterministic bounded change plan is
returned rather than a generic insufficient-evidence answer. Research runs
return `ResearchRunResult` using the same trace contract as direct RAG.

`recording_store.py` persists run summaries and feedback events in PostgreSQL.
The `monitoring_runs` table stores per-request trace metrics; the
`feedback_events` table stores useful/not-useful feedback. Both are linked by
`session_id` for dashboard aggregation. A `NoOpRecordingStore` is used when
PostgreSQL is not configured.

`monitoring.py` provides opt-in Logfire instrumentation for FastAPI and
PydanticAI. It complements the PostgreSQL-backed dashboard; it does not replace
persisted reviewer-visible monitoring data.

`frontend/` is a vendored React TypeScript app using TanStack Router and Query.
It is a client of the FastAPI contract: it submits question mode, retrieval
mode, limit, research kind (direct/agentic), and session ID, then renders
the answer, evidence, trace metadata, model usage, cost telemetry, research
steps, and change targets. The monitoring route renders real PostgreSQL-backed
dashboard panels. Feedback controls allow useful/not-useful submission with
optional comments. Browser access is enabled only when FastAPI CORS origins
are configured.

`pricing.py` keeps OpenAI cost estimation separate from answer generation.
Unknown model prices, explicit empty pricing overrides, and inconsistent provider
usage metadata produce unknown cost fields rather than failing the RAG run.

## Docker Compose services

```text
qdrant       Qdrant v1.15.1 vector database
postgres     PostgreSQL 17 for monitoring and feedback persistence
api          FastAPI backend (Python 3.12, uv)
frontend     React TypeScript frontend (Node 22, Vite)
```

All services have health checks. The API depends on healthy Qdrant and
PostgreSQL; the frontend depends on a healthy API.
