# v0.5.5 monitoring detail plan

## Summary

`v0.5.4` has a working reviewer-visible monitoring page, but the output is
mostly aggregate. `v0.5.5` should make persisted monitoring inspectable at the
run level: reviewers should be able to see which runs happened, what each run
did, what it cost, whether it used tools, and whether feedback or errors were
recorded.

Keep this as a small monitoring-detail release. Do not add Grafana, a new
telemetry backend, authentication, or prompt/source-content persistence.

Logfire status: Logfire is already present as opt-in FastAPI and PydanticAI
instrumentation. It is useful for external traces when explicitly enabled, but
PostgreSQL remains the reviewer-visible monitoring source of truth for this
release.

## Current state

Already available:

- `monitoring_runs` persists one row per direct or agentic run.
- `feedback_events` persists useful/not-useful feedback linked by `session_id`
  and optional `request_id`.
- `GET /monitoring/summary` returns dashboard aggregates.
- `/monitoring` renders the aggregate dashboard from PostgreSQL-backed data.

Current limitation:

- The UI does not expose individual run rows.
- Reviewers cannot inspect a run's repository, commit, retrieval settings,
  tool-call count, model usage, error detail, or linked feedback.
- The persisted row does not include original question text, rewritten queries,
  retrieved file list, or individual tool-call sequence.

## Scope

In scope:

- Backend typed models for monitoring run summaries and run details.
- `GET /monitoring/runs` for recent run history.
- `GET /monitoring/runs/{request_id}` for one run detail.
- Frontend monitoring table with recent runs.
- Frontend run detail panel, route, or sheet.
- Minimal filters for run kind, repository, error status, feedback state, and
  limit.
- Tests for backend storage/API and frontend rendering.
- Documentation updates for reviewer monitoring checks.

Out of scope:

- Grafana or another dashboard stack.
- Storing answer text, prompt text, source-code excerpts, or full evidence
  content in monitoring tables.
- Production auth or admin-only routing.
- New evaluation execution UI.
- A database migration framework.

## Data contract

Add typed response models:

- `MonitoringRunSummary`
  - `request_id`
  - `session_id`
  - `run_kind`
  - `started_at`
  - `completed_at`
  - `repository_name`
  - `branch`
  - `commit_hash`
  - `question_mode`
  - `retrieval_mode`
  - `retrieved_chunk_count`
  - `unique_file_count`
  - `evidence_count`
  - `latency_ms_total`
  - `latency_ms_retrieval`
  - `latency_ms_model`
  - `tool_call_count`
  - `insufficient_evidence`
  - `has_error`
  - `feedback_useful`
  - `feedback_not_useful`
  - `total_estimated_cost_usd`

- `MonitoringRunDetail`
  - all summary fields
  - `repository_id`
  - `retrieval_limit`
  - `error_type`
  - `error_message`
  - `model_usage`
  - linked feedback rows with `submitted_at`, `useful`, and optional comment

Keep `/monitoring/summary` unchanged for compatibility.

## Backend implementation steps

1. Extend models.
   - Add `MonitoringRunSummary`, `MonitoringRunDetail`,
     `MonitoringRunList`, and `MonitoringRunFeedback` to `models.py`.
   - Keep response fields scalar and JSON-safe.

2. Extend recording store protocol.
   - Add `list_monitoring_runs(...)`.
   - Add `get_monitoring_run(request_id: str)`.
   - Return empty list for `NoOpRecordingStore`.
   - Return `None` for missing details.

3. Add SQL queries.
   - List recent runs ordered by `completed_at DESC`.
   - Join or aggregate feedback counts per `request_id` and `session_id`.
   - Detail query loads one row plus linked feedback events.
   - Add index on `monitoring_runs (completed_at DESC)` if needed.

4. Add API routes.
   - `GET /monitoring/runs?limit=50&run_kind=&repository_name=&has_error=&feedback=`
   - `GET /monitoring/runs/{request_id}`
   - Return `404` for unknown `request_id`.
   - Validate `limit` with a small maximum, for example `100`.

5. Keep failure behavior stable.
   - Do not expose stack traces.
   - Do not expose prompt text, answer text, source content, auth headers, or
     environment values.

## Frontend implementation steps

1. Add client types and API calls.
   - Add monitoring run list/detail types to `rag-types.ts`.
   - Add `getMonitoringRuns` and `getMonitoringRunDetail` to `rag-client.ts`.

2. Upgrade `/monitoring`.
   - Keep the existing summary cards at the top.
   - Add a recent runs table below the cards.
   - Columns: time, kind, repository, commit, retrieval mode, chunks/files,
     latency, tokens/cost, feedback, status.
   - Use compact table rows, not large cards.

3. Add details interaction.
   - Clicking a row opens a right-side detail panel, detail section below the
     table, or sheet.
   - Show repository identity, timings, retrieval counts, model usage, tool-call
     count, insufficient-evidence flag, error detail, and feedback comments.
   - For direct runs, make clear that tool-call count is expected to be zero.

4. Add filters.
   - Run kind: all, direct, agentic.
   - Status: all, error, no error.
   - Feedback: all, useful, not useful, none.
   - Limit: 25, 50, 100.

5. Preserve empty states.
   - No runs: existing honest empty state.
   - Runs but no detail selected: compact prompt to select a row.
   - Missing detail: show a stable not-found message.

## Tests

Backend:

- `PostgresRecordingStore.list_monitoring_runs` returns recent rows in
  descending completion order.
- List query includes feedback counts.
- Filters by run kind, error status, feedback state, repository name, and limit.
- Detail query returns model usage, error fields, and feedback rows.
- Missing detail returns `404` through the API.
- `NoOpRecordingStore` returns empty list and missing detail.

Frontend:

- Monitoring route renders aggregate cards and recent run table.
- Filters call the list endpoint with expected query params.
- Selecting a run loads and renders detail.
- Error detail and feedback comments render without layout overflow.
- Empty and missing-detail states remain honest.

## Validation

Run narrow checks first:

```bash
uv run pytest tests/test_recording_store.py tests/test_api.py -q
npm test -- --run src/routes/-monitoring.test.tsx src/lib/rag-client.test.ts
```

Then run full validation:

```bash
make test-all
make compose-up
```

Current validation notes:

- `uv run pytest tests/test_recording_store.py tests/test_api.py -q`: passed.
- `make frontend-test`: passed.
- `make frontend-typecheck`: passed.
- `make frontend-lint`: passed with existing shadcn fast-refresh warnings only.
- `make test-all`: passed with 109 backend tests and 38 frontend tests.
- `make compose-up`: passed with API, frontend, PostgreSQL, and Qdrant healthy.
- Runtime smoke through the frontend proxy passed for `GET /api/monitoring/runs`
  and `GET /api/monitoring/runs/{request_id}`.

Manual reviewer smoke:

1. Start the stack with `make compose-up`.
2. Ingest a public GitHub repository.
3. Run one direct query and one agentic query.
4. Submit useful or not-useful feedback for at least one run.
5. Open `/monitoring`.
6. Confirm scoped aggregate cards, monitoring charts, recent run table,
   filters, and run detail sheet all show persisted PostgreSQL-backed data.

## Exit condition

`v0.5.5` is complete when a reviewer can inspect both aggregate monitoring and
individual run details from the browser after running direct and agentic
queries. The release should show at least five useful aggregate panels plus a
recent run table and one-click detail view backed by persisted PostgreSQL data.

Current `dev` note: PR #11 and PR #12 extended this with six chart panels,
run-first layout, current-scope aggregation, loaded-run date slicers, a separate
all-time persisted summary, and a right-side run detail sheet.

## Risks

- Persisted data is currently intentionally minimal. Original question text,
  rewritten queries, retrieved filenames, and exact tool sequence are not yet
  stored. If reviewers need those, add a later explicit trace-persistence
  decision instead of quietly storing prompts or source snippets.
- The details view must stay compact; the dashboard is an operator surface, not
  a marketing page.
- PostgreSQL schema changes are still managed by idempotent SQL. Keep additions
  backward-compatible.
