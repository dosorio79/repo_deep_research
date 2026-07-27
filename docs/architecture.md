# Architecture

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
research.py -- direct RAG, citation validation, and answer evaluation
        |
        v
repo-research CLI / FastAPI -- JSON evidence and grounded answers
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

`research.py` adds the M3 direct-RAG layer. It assigns opaque evidence IDs to
retrieved chunks, asks the answer model to cite only those IDs, then maps valid
IDs back to canonical paths, symbols, and line ranges from storage. Unknown
citations or empty retrieval results return explicit insufficient-evidence
answers. The minimal FastAPI app keeps routes thin and delegates orchestration
to the same service used by the CLI.
