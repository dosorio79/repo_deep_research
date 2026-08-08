# Capstone MVP milestone plan

## Goal

Get Repo Deep Research to a reviewable LLM Zoomcamp capstone MVP as quickly as
possible without expanding beyond the PRD's Python-repository research scope.

This is now the next delivery milestone. It bundles the remaining M4/M5 work
needed for peer-review scoring; it does not replace the longer product roadmap.

The MVP should make every scoring area visible to a peer reviewer:

- problem statement and data source;
- repository ingestion into Qdrant;
- retrieval plus LLM answer flow;
- retrieval and answer evaluation;
- browser or API interface;
- user feedback and monitoring dashboard;
- Docker Compose reproducibility;
- README rubric map with commands, screenshots, and example outputs.

Source guideline: DataTalksClub `project.md` asks for an end-to-end RAG or
agent application that ingests a non-course dataset, retrieves context, calls an
LLM, evaluates retrieval and final output, exposes an interface, collects
feedback, monitors the application, and documents how reviewers can run it.

## Current state

Already strong enough for MVP evidence:

- Non-course data source: this repository's own Python, Markdown, TOML, YAML,
  and JSON files.
- Ingestion: local parser plus Qdrant indexing through `repo-research ingest`
  and `make ready`.
- Retrieval: dense, sparse, and Qdrant RRF-hybrid modes.
- Retrieval evaluation: 30 versioned development and held-out questions with
  dense selected as the current production default.
- Direct RAG: `/rag` and `repo-research rag` return structured answers with
  validated citations and trace metadata.
- Interface: React TypeScript frontend for direct RAG, currently shaped as a
  backend testing harness / future backoffice.
- Agentic slice: `/research` and `repo-research research` exist on `dev` after
  the M4 service work.
- CI and release governance: `main` production, `dev` integration.

Main gaps for capstone scoring:

- PR #6 needs to merge before starting a new implementation slice.
- Live M4 agentic smoke is not yet audited with `OPENAI_API_KEY`.
- Frontend does not yet expose the Direct/Agentic selector.
- The current frontend is not the ideal client-facing product. It is useful for
  reviewer evidence and backoffice operations, but the MVP needs either a
  cleaner client-facing research route or very explicit documentation that the
  submitted interface is an operator/reviewer harness.
- Backoffice routes should be reachable from the main frontend but gated as
  admin-only. For the capstone MVP, use a lightweight demo/admin gate rather
  than full account, role, OAuth, or multi-tenant authentication.
- Feedback is not persisted.
- Monitoring has only latest-run local UI, not a persistent dashboard with at
  least five charts.
- Docker Compose currently runs Qdrant only, not the full app.
- README does not yet include a compact rubric-to-evidence map, screenshots, or
  final measured answer-evaluation results.
- Query rewriting and reranking are PRD/best-practice points but not required
  to make the MVP reviewable; implement only after core capstone gaps.

## Target MVP score posture

Aim for full points in the standard rubric before chasing bonus:

| Area | MVP target |
|---|---|
| Problem description | README and PRD clearly explain unfamiliar-repo research. |
| Retrieval flow | Qdrant retrieval plus OpenAI direct RAG and bounded agentic research. |
| Retrieval evaluation | Dense/sparse/hybrid evaluated; best measured mode used. |
| LLM evaluation | Compare direct RAG and bounded agentic research on the same records. |
| Interface | FastAPI plus a simple client-facing research screen; keep monitoring/evaluation as backoffice. |
| Ingestion pipeline | Automated CLI/Make pipeline; optional Compose service command. |
| Monitoring | Feedback persisted and dashboard shows at least five charts. |
| Containerization | Full app stack in Docker Compose, not Qdrant only. |
| Reproducibility | One clear reviewer path with pinned dependencies and env examples. |
| Best practices | Hybrid search is already evaluated; defer reranking/query rewriting unless time remains. |

## Fast implementation sequence

### 0. Finish branch hygiene

Status: complete for the documentation PR setup.

1. Merge PR #6 into `dev` after checks remain green.
2. Delete the merged fix branch locally and remotely.
3. Start MVP work from updated `dev`.

Exit condition: `dev` is clean, current, and contains M4 plus settings-test
isolation.

### 1. Audit current M4

Purpose: turn existing agentic backend work into reviewer evidence.

Tasks:

1. Run a live self-repository smoke with `OPENAI_API_KEY`:

   ```bash
   make ready
   uv run repo-research research "which modules must change to add feedback persistence?" --mode change
   ```

2. Capture one audited example in docs, including evidence paths, trace fields,
   tool-call counts, cost metadata if available, and any quality issues.
3. Add or adjust only small tests/docs if the live smoke exposes contract drift.

Exit condition: M4 is demonstrably usable through CLI and API with bounded tool
calls and grounded citations.

### 2. Split frontend into client-facing research and backoffice

Purpose: make both LLM approaches reviewable from the UI without presenting the
testing harness as the final user product.

Tasks:

1. Keep the existing shell and Monitoring/Evaluations/Feedback navigation as an
   operator/reviewer backoffice, but move it under an admin route group.
2. Add or reshape the first route into a cleaner client-facing research screen:
   question, mode, Direct/Agentic selector, concise answer, evidence, and
   feedback. Advanced settings, raw JSON, trace, and operational metadata should
   be collapsible or moved to the backoffice/debug area.
3. Use this route shape:

   ```text
   /                  client-facing research UI
   /admin             admin/backoffice shell
   /admin/monitoring
   /admin/evaluations
   /admin/feedback
   /admin/settings
   ```

4. Gate `/admin/*` with a simple MVP admin mechanism such as
   `RDR_ADMIN_TOKEN`. Do not add full user accounts, roles, OAuth, or
   production-grade authentication in the capstone MVP.
5. Direct continues calling `POST /rag`.
6. Agentic calls `POST /research`.
7. Reuse the existing answer/evidence/trace rendering where it helps, but do not
   let raw trace panels dominate the client-facing view.
8. Show `research_steps` and nonzero `tool_call_count` only for agentic runs.
9. Keep admin Evaluations, Feedback, Monitoring, and Settings honest until the
   backend features exist; after M5 they become the reviewer/operator
   backoffice.

Exit condition: reviewer can compare direct RAG and agentic research from the
same UI without changing commands, and the README clearly distinguishes the
client-facing research screen from the admin/backoffice harness.

### 3. Persist feedback and run telemetry

Purpose: unlock monitoring points with durable Postgres-backed run and feedback
records.

Tasks:

1. Add PostgreSQL as the persistence store for monitoring and feedback.
2. Persist `RagRunTrace` / `ResearchRunResult` summary metadata after successful
   `/rag` and `/research` responses.
3. Store monitoring and feedback in separate tables connected by `session_id`;
   retain `request_id` as the identifier for a single returned run.
4. Add `POST /feedback` with useful/not-useful, optional comment, `session_id`,
   request ID, and run mode.
5. Add `GET /monitoring/summary` for dashboard aggregates.
6. Add opt-in Logfire instrumentation for FastAPI and PydanticAI.
7. Add focused tests for schema creation, insert/read paths, aggregate queries,
   API contracts, and frontend session propagation.

Keep it simple:

- no authentication;
- no background workers;
- no event bus;
- no ORM or migration framework in this milestone;
- no SQLite fallback;
- no full source content in telemetry.

Exit condition: feedback and run summaries survive process restart in a local
PostgreSQL database and can be joined by `session_id`.

### 4. Build the monitoring dashboard

Purpose: satisfy the "feedback plus at least five charts" monitoring target.

Tasks:

1. Add backend read endpoints for dashboard aggregates.
2. Implement the Monitoring route with real persisted data as a backoffice
   surface, not as part of the client-facing question flow.
3. Include at least five useful panels:
   - total runs by mode over time;
   - average latency by mode;
   - retrieved chunk count / unique file count distribution;
   - token usage and estimated cost by model;
   - feedback useful vs not useful;
   - error count by error type if present.
4. Add empty states that say no data exists rather than inventing sample data.

Exit condition: after a few local `/rag` and `/research` runs plus feedback,
the dashboard renders real charts from PostgreSQL-backed data.

### 5. Containerize the full reviewer path

Purpose: move from dependency-only Compose to full app Compose.

Tasks:

1. Add a backend Dockerfile for the FastAPI app.
2. Add a frontend production build container or serve the built frontend from a
   lightweight static service.
3. Extend `docker-compose.yml` with Qdrant, API, and frontend services.
4. Mount a local repository path for self-ingestion.
5. Document required env vars, especially `OPENAI_API_KEY`.
6. Add a smoke command for health and one sample request.

Exit condition: `docker compose up --build` starts Qdrant, API, and UI, and the
README includes the exact reviewer path.

### 6. Final evaluation and README rubric map

Purpose: make scoring easy.

Tasks:

1. Re-run retrieval evaluation on development and held-out data after final
   ingestion.
2. Add an answer-evaluation comparison:
   - direct RAG baseline;
   - bounded agentic research.
3. Record summary metrics in `docs/evaluation.md`; do not commit ignored raw
   result files unless intentionally versioned.
4. Update README with:
   - capstone problem statement;
   - dataset/source explanation;
   - one-command setup;
   - screenshots for the client-facing research screen and the backoffice
     monitoring dashboard;
   - example direct and agentic questions;
   - rubric table mapping each criterion to repo files/commands;
   - known limitations and honest metric summary.

Exit condition: a peer reviewer can score the project from the README without
reverse-engineering the repo.

## Optional after MVP

Only start these after the core rubric is covered:

1. Query rewriting behind a flag, evaluated against no-rewrite.
2. Reranking behind a flag, evaluated against dense baseline.
3. Optional public GitHub clone ingestion.
4. Cloud deployment bonus.

## Proposed branch order

1. `docs/capstone-mvp-plan` - this plan only.
2. `feat/mvp-agentic-ui` - live M4 audit plus Direct/Agentic UI.
3. `feat/mvp-feedback-monitoring` - PostgreSQL feedback, monitoring dashboard,
   and opt-in Logfire instrumentation. See
   `docs/plans/mvp-postgres-feedback-monitoring.md`.
4. `feat/mvp-compose-docs` - full Compose, final evaluation, README rubric map.

Keep PRs small enough to review, but do not create more branches than needed:
the goal is a finished capstone, not perfect milestone ceremony.

## Validation checklist

For implementation PRs:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make lint
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make typecheck
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make test
make frontend-test
make frontend-typecheck
make frontend-build
```

For final reviewer proof:

```bash
docker compose up --build
make ready
make evaluate-retrieval
uv run repo-research evaluate-answers --dataset eval/held_out.json --output eval/results/answer-held-out.json
```

Live answer and agentic evaluation require `OPENAI_API_KEY`.
