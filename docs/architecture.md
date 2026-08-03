# Architecture

## Working layers

```text
Makefile
  Thin developer shortcuts: ready, evidence, rag, api, api-rag, frontend-*.

Entry points
  repo-research CLI for local commands.
  FastAPI for the browser frontend and HTTP contract tests.
  React TypeScript frontend under frontend/ for manual RAG testing.

Runtime composition
  runtime.py creates shared database, model, and direct-RAG dependencies.

Service layer
  rag.py runs direct RAG, citation validation, and answer evaluation.

Retrieval and storage
  db.py owns FastEmbed, Qdrant payloads, and dense/sparse/hybrid search.

Ingestion
  ingestion.py discovers files, records Git identity, filters, and parses.
```

Both `make rag` and `make api-rag` reach the same `DirectRagService` through the
same runtime composition module. The difference is the entry point: `rag` calls
the CLI directly, while `api-rag` posts to FastAPI `/rag` and exercises the
HTTP contract that the frontend uses.

## Data Flow

```text
Local repository path
        |
        v
ingestion.py -- filters, Git identity, and parsing
        |
        v
db.py -- FastEmbed (local ONNX), current chunk payloads, and vector search
        |
        v
rag.py -- direct RAG, citation validation, and answer evaluation
        |
        v
repo-research CLI / FastAPI -- JSON evidence and grounded answers
        |
        v
frontend/ -- browser RAG testing harness for answer, evidence, and trace display
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
where pricing is known, and direct-RAG tool-call count. The minimal FastAPI app
keeps routes thin and delegates orchestration to the same service used by the
CLI.

`frontend/` is a vendored React TypeScript app. It is deliberately
a client of the FastAPI `/rag` contract: it submits question mode, retrieval
mode, limit, optional repository path, and API base URL, then renders
`RagRunResult.answer`, evidence, trace metadata, model usage, cost telemetry,
and raw JSON. Planned Evaluations, Monitoring, Feedback, and Settings routes
reserve backoffice navigation space without fake operational data or persistence
flows. Browser access is enabled only when FastAPI CORS origins are configured.

`pricing.py` keeps OpenAI cost estimation separate from answer generation.
Unknown model prices, explicit empty pricing overrides, and inconsistent provider
usage metadata produce unknown cost fields rather than failing the RAG run.
