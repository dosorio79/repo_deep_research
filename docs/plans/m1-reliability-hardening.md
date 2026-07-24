# M1.1 — Ingestion reliability hardening

## Goal

Make the existing local dense-ingestion baseline safe to retry before M2 adds
sparse, hybrid, and evaluated retrieval.

## Scope

- validate embedding count and vector dimensions before deleting existing points;
- upsert replacement chunks before deleting stale chunk IDs, so an embedding or
  validation failure retains the last successful index;
- scope dense search to both repository and current commit identity;
- continue parsing when one eligible file has a decoding, filesystem, or syntax
  error, and report a typed path-scoped diagnostic;
- emit the typed ingestion summary from the CLI;
- add focused regression tests for replacement safety, stale cleanup,
  partial parsing, and CLI ingestion output.

## Non-goals

- incremental commit comparison or historical repository browsing;
- sparse/hybrid retrieval, evaluation, orchestration, API, or monitoring;
- a new service or adapter layer.

## Affected tests

- parser diagnostics for invalid Python source;
- Qdrant replacement after an embedding validation failure;
- same-commit stale-point cleanup and commit-scoped search;
- CLI ingestion JSON output, including skipped-file diagnostics.

## Implementation steps

1. Extend the typed ingestion and search boundary models.
2. Make parsing collect per-file diagnostics without hiding successful chunks.
3. Stage Qdrant replacement: read existing IDs, validate embeddings, upsert new
   points, then delete only stale IDs.
4. Expose the summary through the CLI and cover the observable behavior.
5. Run formatting, linting, type checks, unit tests, and Compose validation.

## Outcome

Completed on 2026-07-24.

- The database now reads existing point IDs, validates embedding count and
  dimensions, upserts new chunks, then removes only stale IDs.
- Search filters by repository and commit identity, preventing stale commits
  from being returned during or after replacement.
- Parsing records path-scoped `SyntaxError`, `UnicodeError`, and `OSError`
  diagnostics while retaining successful chunks. When every eligible file
  fails, the CLI leaves the prior index untouched.
- Regression coverage verifies partial parsing, replacement safety after a
  vector-dimension failure, stale cleanup, and CLI diagnostics.

## Validation

Completed on 2026-07-24:

- `make lint` — passed;
- `make typecheck` — passed (strict mypy, 12 source files);
- `make test` — passed (16 tests);
- `docker compose config --quiet` — passed.
