# M2 — Evaluated hybrid retrieval

## Goal

Provide dense, sparse, and RRF-hybrid repository retrieval through one typed
query boundary, then select the production default from a deterministic local
evaluation report.

## Scope

- named Qdrant vectors: `dense` and `sparse`;
- FastEmbed dense and sparse encoders, configured independently;
- `dense`, `sparse`, and `hybrid` retrieval modes using Qdrant RRF;
- a shared `SearchResult` output shape;
- versioned JSON development and held-out ground-truth records under `eval/`;
- deterministic file- and symbol-level retrieval metrics plus a JSON report;
- CLI commands for mode-specific search and retrieval evaluation.

## Decisions

- Use Qdrant named vectors and its RRF fusion query; no custom fusion weights.
- Use `Qdrant/bm25` as the lightweight FastEmbed-compatible sparse default.
- Change the default collection to `repo_chunks_v2` because an existing M1
  collection uses an incompatible unnamed-vector schema. Users must re-ingest.
- Keep evaluation in the standard library with JSON records and reports; no
  dataframe dependency is needed for the initial deterministic metrics.
- Do not implement query rewriting or reranking: both are later, evaluated
  improvements and are outside M2's baseline.

## Affected tests

- dense, sparse, and hybrid results use the same typed result shape;
- indexing rejects malformed sparse embeddings without deleting prior points;
- metric calculations cover hits, misses, and file/symbol distinctions;
- evaluation records load and each mode writes a deterministic report;
- CLI accepts retrieval mode and evaluation commands.

## Implementation steps

1. Extend configuration and typed query/evaluation models.
2. Add sparse embedding and named-vector indexing to the existing database.
3. Add mode-aware search and a minimal evaluation module/CLI.
4. Add versioned development and held-out ground truth.
5. Update documentation and validate the full suite.

## Outcome

Completed on 2026-07-24.

- `RepositoryDatabase` now stores named `dense` and `sparse` vectors and offers
  dense, sparse, and Qdrant RRF-hybrid modes through `SearchQuery`.
- Development and held-out JSON datasets each contain 15 validated questions;
  together they cover ten locate, ten flow, and ten change-impact prompts.
- The CLI produces deterministic JSON reports, and `RDR_RETRIEVAL_MODE=dense`
  is the configured default after the held-out comparison favored dense across
  every reported metric.
- The M2 collection is `repo_chunks_v2`; an M1 collection must be re-ingested
  because its unnamed-vector schema is incompatible.

## Validation

Completed on commit `5e23291`:

- `make lint` — passed;
- `make typecheck` — passed (strict mypy, 14 source files);
- `make test` — passed (20 tests);
- `docker compose config --quiet` — passed;
- local Qdrant ingestion — passed (265 points, 530 named vectors);
- development and held-out retrieval comparisons — completed; dense selected
  from held-out results recorded in `docs/evaluation.md`.
