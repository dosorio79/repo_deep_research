# M1 architecture

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
repo-research CLI -- JSON evidence
```

`ParsedChunk` is the boundary between parsing and storage. It carries the
repository and commit identity, path, symbol, parent symbol, line range,
content, contextual metadata, and deterministic content/point IDs. Qdrant
persists that complete payload, allowing the CLI to return evidence rather than
only text snippets.

`RepositoryDatabase` replaces all points for one repository identity during ingestion.
This is intentionally simple and makes re-ingestion idempotent; incremental
commit comparison is deferred. M1 uses only cosine dense retrieval. Sparse
vectors, fusion, rewriting, and reranking are M2+ work.
