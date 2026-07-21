# M1 — Searchable repository

## Goal

Deliver the first end-to-end, local-only repository research slice: discover a
Python repository, create typed evidence chunks, index deterministic dense
vectors in Qdrant, and return evidence through a CLI search command.

## Scope

Included:

- local repository discovery and Git identity;
- practical root `.gitignore` support plus mandatory ignored directories and
  configurable size limits;
- AST extraction for Python modules, classes, functions, and methods;
- Markdown heading chunks and whole-file JSON/YAML/TOML configuration chunks;
- typed repository, chunk, search-query, and search-result models;
- Qdrant dense-vector indexing with replacement semantics for idempotency;
- a `repo-research ingest` and `repo-research search` CLI;
- unit and Qdrant-local integration tests.

Deferred to later milestones: sparse/hybrid retrieval, query rewriting,
reranking, answer generation, PydanticAI, API/UI, feedback, and monitoring.

## Simplification update

The first implementation separated loader, parser, service, embedding protocol,
and Qdrant storage into several small modules. That was more abstraction than
M1 needs. The final M1 code keeps only four implementation files:

- `models.py` for typed evidence data;
- `ingestion.py` for discovery and parsing;
- `db.py` for local ONNX embedding and Qdrant operations;
- `cli.py` for command orchestration.

This retains testable boundaries without introducing a service layer, adapter
protocol, or package hierarchy before M2 needs them.

## Implementation plan

1. Add the smallest required dependencies: Qdrant client, FastEmbed for local
   dense embeddings, and PathSpec for `.gitignore` patterns. Extend settings
   only for ingestion and dense-index configuration.
2. Define validated Pydantic models and deterministic IDs/content hashes so
   every chunk preserves repository, commit, path, symbol, line, type, and
   context evidence.
3. Implement discovery and parsers. The loader filters irrelevant files before
   parsing; parsers preserve line ranges and structural context.
4. Implement direct local embedding and Qdrant operations in `db.py`.
   Replacing all points for a repository identity on each ingest prevents stale
   or duplicate current results.
5. Implement a thin argparse CLI that orchestrates ingestion or dense search
   and emits readable JSON evidence.
6. Add focused fixtures and tests for filters, AST metadata/line ranges,
   Markdown headings, hashes/validation, Qdrant result shapes, idempotency, and
   the CLI boundary.
7. Update setup/usage/architecture documentation, run the required quality
   suite, and manually ingest/search this repository with Qdrant.

## Course-repository inspiration

The linked `dosorio79/llm-zoomcamp` repository’s `cli_rag` example informed the
CLI-first local workflow and its uv-managed reproducibility. This milestone
does not reuse its code: its domain and storage design differ from the
repository-evidence requirements here.

## Affected tests

- discovery and ignore rules;
- Python/Markdown/config parser chunks and line ranges;
- model IDs and validation;
- Qdrant dense indexing/search/idempotency;
- CLI orchestration with injected fakes.

## Acceptance checklist

- [x] Local repository identity includes name, branch, and commit hash.
- [x] Filtering excludes Git metadata, environments, caches, generated/binary,
  ignored, and oversized files.
- [x] Python, Markdown, YAML, TOML, and JSON files produce typed chunks with
  valid paths and line ranges.
- [x] Python chunks preserve imports, signatures, decorators, docstrings, and
  parent symbols where applicable.
- [x] Dense Qdrant indexing is idempotent and current-only for a repository.
- [x] CLI ingestion and dense search return repository evidence.
- [x] Tests, linting, and type checking pass; self-repository smoke test is
  documented below.

## Validation results

Completed on 2026-07-21:

- `make format` — passed
- `make lint` — passed
- `make typecheck` — passed (`mypy`: 18 source files)
- `make test` — passed (12 tests, including an in-memory Qdrant integration
  test)
- `docker compose config --quiet` — passed
- Qdrant HTTP client connectivity — passed with aligned `v1.15.1` client and
  container versions
- bounded self-repository CLI smoke test — passed with
  `RDR_MAX_FILE_SIZE_BYTES=1000`: indexed 12 chunks for branch `main` at commit
  `82d8155def72ac74944ea02fe7fbe4a82f8d30b4`, then returned typed dense results
  including `pyproject.toml` configuration evidence

Unexpected findings:

- FastEmbed's default 256-document batch is unnecessarily large for local
  repository ingestion. `RDR_EMBEDDING_BATCH_SIZE=16` is now the documented,
  configurable default; a complete 223-chunk local embedding run succeeded.
- Qdrant client `1.15.1` warned against the M0 server `1.13.4`, so Docker
  Compose now pins the matching `qdrant/qdrant:v1.15.1` image.
- The initial M1 package hierarchy was flattened after review. The final
  implementation has no loader/parser/service/embedder adapter packages;
  validation after the refactor passed with 12 tests and strict mypy across 12
  source files.
