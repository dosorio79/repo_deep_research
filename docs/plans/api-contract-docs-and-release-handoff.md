# API Contract, Swagger, and Release Handoff

## Purpose

Capture the next small product/documentation slice and the release handoff for
the next working session. The current priority is to make the API contract easy
to inspect and reuse while keeping the application workflow simple.

## Current Branch Context

- Active PR: evidence snippet inspection from research results.
- Branch: `feat/inspectable-evidence-snippets`.
- Current package version: `0.5.5`.
- Release work is intentionally deferred to the next session after the current
  feature PR is merged into `dev`.

## Next Feature Branch

Recommended branch:

```bash
git checkout dev
git pull --ff-only origin dev
git checkout -b feat/api-contract-docs
```

## API Contract And Swagger Scope

1. Export the FastAPI OpenAPI schema to a versioned file such as
   `docs/api/openapi.json`.
2. Add a lightweight contract-generation command or script. Prefer a direct
   command if adding another public Make target would make the interface noisy.
3. Confirm the local Swagger UI and schema endpoints work:

```text
GET /docs
GET /openapi.json
```

4. Add or update endpoint tags, summaries, and descriptions so Swagger groups
   the API by operator task:

- health and metadata;
- repository ingestion;
- direct RAG;
- agentic research;
- feedback;
- monitoring;
- evaluation.

5. Add a contract smoke test that generates the OpenAPI schema without live
   Qdrant or OpenAI dependencies and asserts expected paths and schema names.

## Documentation Updates

Create or update:

- `docs/api.md`: API overview, local Swagger URL, schema export command, and
  compact endpoint map.
- `docs/setup.md`: link to API docs after local stack startup.
- `docs/usage.md`: link direct RAG, agentic research, monitoring, and
  evaluation workflows to their API endpoints.
- `README.md`: add a short "API contract" link under deeper docs.

Keep examples compact and stable. Do not paste large generated OpenAPI output
into prose docs.

## Quick Wins

- Ensure `/health` and root API metadata expose enough version/status
  information for local checks.
- Add compact request/response examples for:
  - `POST /repositories/ingest`;
  - `POST /rag`;
  - `POST /research`;
  - `GET /monitoring/runs/{request_id}`;
  - `GET /evaluations/results`.
- Verify evaluation responses expose only the current rubric field names.
- Keep Swagger readable by avoiding generic route descriptions.

## Release Handoff For Next Session

After the current feature PR is merged into `dev`:

1. Sync `dev` and verify it is clean.
2. Run release validation:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make lint
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make typecheck
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make test
cd frontend
npm run lint
npm run typecheck
npm test
```

3. Decide whether the release should keep package version `0.5.5` or bump to a
   new patch version before promotion.
4. Open a promotion PR from `dev` to `main`.
5. After merge to `main`, create and push the release tag from `main`.

The release should include the current monitoring, evaluation, rigorous rubric,
and inspectable evidence improvements. Do not re-run or replace persisted local
evaluation rows as part of the release unless there is a specific reason to
refresh local demo data.

## Non-Goals

- No database schema changes for this slice.
- No frontend redesign beyond links to API docs if needed.
- No generated SDK.
- No live repository reads for evaluation evidence.
