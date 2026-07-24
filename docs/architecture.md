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

`RepositoryDatabase` stages a replacement by validating embeddings and upserting
new chunks before deleting stale point IDs. This retains the previous searchable
index if embedding validation or upsert fails. Dense search is scoped to both
repository and commit identity, and stale points are removed after a successful
replacement. Incremental commit comparison is deferred. M1 uses only cosine
dense retrieval. Sparse vectors, fusion, rewriting, and reranking are M2+ work.

`ingestion.py` reports decoding, filesystem, and syntax failures for individual
eligible files without discarding successfully parsed chunks. The CLI emits
those diagnostics alongside the repository identity and indexed-chunk count.
