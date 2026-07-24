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
