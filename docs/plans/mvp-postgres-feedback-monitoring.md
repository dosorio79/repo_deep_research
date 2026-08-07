# MVP PostgreSQL feedback, monitoring, and Logfire plan

## Summary

This is the next implementation milestone after the `v0.4.0` release is
completed and local branches are synchronized.

The slice persists monitoring and feedback in PostgreSQL as the system of
record. Monitoring run rows and feedback rows live in separate tables connected
by `session_id`, while `request_id` remains the identifier for one returned RAG
or agentic research response.

Logfire is added as opt-in application instrumentation for FastAPI and
PydanticAI. It complements the PostgreSQL-backed dashboard; it does not replace
persisted reviewer-visible monitoring data.

## Scope

In scope:

- PostgreSQL-backed run telemetry persistence.
- PostgreSQL-backed feedback persistence.
- `session_id` propagation from frontend to `/rag`, `/research`, and
  `/feedback`.
- Backend monitoring aggregate endpoint for dashboard panels.
- Frontend feedback controls and monitoring dashboard backed by API data.
- Opt-in Logfire instrumentation for FastAPI and PydanticAI.
- Docker Compose PostgreSQL service for local reviewer runs.

Out of scope:

- SQLite fallback persistence.
- Production authentication or role management.
- Moving backoffice routes under `/admin/*`.
- Grafana or another dashboard stack.
- Persisting prompts, answer text, source content, evidence excerpts, secrets,
  or full environment values.

## Backend design

Use the standard Postgres driver directly and keep the storage layer explicit.
Do not add an ORM or migration framework in this milestone.

Settings:

- `RDR_POSTGRES_DSN`: Postgres connection string for local and Compose runs.
- `RDR_TELEMETRY_ENABLED`: defaults to `true`.
- `RDR_LOGFIRE_ENABLED`: defaults to `false`.
- `RDR_LOGFIRE_SEND_TO_LOGFIRE`: defaults to `false`.

Tables:

- `monitoring_runs`
  - `request_id` primary key.
  - `session_id` indexed, non-empty.
  - run kind: `direct` or `agentic`.
  - repository, branch, commit, question mode, retrieval mode, limits, counts,
    latency fields, tool-call count, insufficient-evidence flag, error fields,
    token totals, estimated cost, and timestamps.
- `feedback_events`
  - generated feedback ID primary key.
  - `session_id` indexed, non-empty.
  - optional `request_id` referencing a run when present.
  - run kind, useful/not-useful flag, optional comment, and submitted timestamp.

API behavior:

- Extend `RagRequest` and `ResearchRequest` with optional `session_id`.
- Add `session_id` to `RagRunTrace` so UI and feedback can link to the persisted
  run.
- Generate a backend UUID `session_id` when callers omit one.
- Persist a monitoring row after each successful `/rag` and `/research`
  response envelope is built, including insufficient-evidence responses and
  normal bounded-error traces.
- Add `POST /feedback` for run-level feedback.
- Add `GET /monitoring/summary` with aggregate data for the dashboard.

## Logfire design

Add opt-in Logfire instrumentation without making Logfire mandatory for local
development or peer review.

- Add the Logfire FastAPI extra dependency.
- Configure Logfire once during app creation only when
  `RDR_LOGFIRE_ENABLED=true`.
- Instrument FastAPI with `logfire.instrument_fastapi(app)`.
- Instrument PydanticAI before agent construction with
  `logfire.instrument_pydantic_ai()`.
- Scrub secrets and avoid adding prompts, full source content, or evidence
  excerpts as custom span attributes.
- Document `LOGFIRE_TOKEN` / local Logfire auth setup as optional.

## Frontend design

- Create or reuse a stable browser-session `session_id`.
- Send `session_id` with direct RAG, agentic research, and feedback requests.
- Add run-level feedback controls beside returned answers:
  useful, not useful, optional comment, and submit.
- Replace the monitoring route's local-storage latest-run view with
  `GET /monitoring/summary`.
- Replace the feedback placeholder route with persisted feedback review.
- Keep empty states honest when no runs or feedback exist.

Required dashboard panels:

- runs by direct versus agentic kind;
- average latency by run kind;
- retrieval volume and unique-file counts;
- token usage and estimated cost by model;
- useful versus not-useful feedback;
- error count by error type when present.

## Tests and validation

Backend tests:

- schema creation is idempotent;
- run insert stores `session_id`, `request_id`, and trace metrics;
- feedback insert stores `session_id` and optional `request_id`;
- monitoring aggregates return stable empty and populated shapes;
- `/rag` and `/research` persist monitoring rows;
- `POST /feedback` stores linked feedback;
- missing `session_id` gets a backend fallback.

Frontend tests:

- direct and agentic requests include `session_id`;
- feedback submission posts `session_id` and `request_id`;
- monitoring renders backend aggregate panels;
- monitoring and feedback empty states are honest.

Validation commands:

```bash
make lint
make typecheck
make test
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

## Exit condition

After local `/rag` and `/research` runs plus submitted feedback, a reviewer can
restart the app and still inspect persisted monitoring and feedback in the UI.
The dashboard shows real PostgreSQL-backed data in at least five useful panels,
and Logfire spans are available when explicitly enabled.

## Implementation progress

- Added typed `session_id`, feedback, and monitoring summary models.
- Added explicit PostgreSQL recording storage for `monitoring_runs` and
  `feedback_events`.
- Wired `/rag` and `/research` to persist run traces when telemetry is
  configured.
- Added `POST /feedback` and `GET /monitoring/summary`.
- Added Docker Compose PostgreSQL and local runtime documentation.
- Wired the frontend to persist browser `session_id`, submit run-level
  feedback, and render API-backed monitoring and feedback summaries.
- Added opt-in Logfire instrumentation for FastAPI and PydanticAI without
  custom prompt, source-content, evidence-excerpt, or header capture.

Remaining before merge:

- Run the full backend and frontend validation suite.
- Smoke-test PostgreSQL persistence against the local Compose database.
