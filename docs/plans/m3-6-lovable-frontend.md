# M3.6 - Lovable Frontend Testing Harness

## Status

Implemented as a vendored Lovable-built frontend under `frontend/`.

## Goal

Build a thin React TypeScript frontend that makes the current direct-RAG backend
easy to test manually. This is a developer/reviewer testing harness, not the full
M5 product and operations milestone.

The first screen should be the usable research interface. Do not build a
marketing landing page.

Leave room for a later application backoffice where evaluation runs, monitoring
dashboards, feedback review, and operational diagnostics can live. M3.6 should
create the navigation and layout shape for that future area, but must not build
the actual backoffice features yet.

## Backend Contract

The frontend calls:

```text
POST http://localhost:8000/rag
```

Request body:

```json
{
  "question": "where is repository configuration validated?",
  "mode": "auto",
  "retrieval_mode": "dense",
  "limit": 5
}
```

Optional request field:

```json
{
  "repository_path": "/absolute/local/path"
}
```

The initial UI should omit `repository_path` by default and let the backend use
its configured repository root. Add repository path as an advanced field only if
it does not distract from the primary workflow.

Allowed modes:

```text
auto
locate
flow
change
```

Allowed retrieval modes:

```text
dense
sparse
hybrid
```

Limit range:

```text
1-20
```

Response body:

```text
RagRunResult
- answer: RagAnswer
- trace: RagRunTrace
```

`answer` fields:

```text
question
mode
summary
implementation_flow[]
evidence[]
relevant_files[]
relevant_symbols[]
change_targets[]
risks[]
confidence
unresolved_questions[]
insufficient_evidence
```

`evidence[]` fields:

```text
evidence_id
path
start_line
end_line
symbol
score
reason
```

`change_targets[]` fields:

```text
path
symbol
reason
evidence_ids[]
```

`trace` fields:

```text
request_id
started_at
completed_at
repository_id
repository_name
branch
commit_hash
question_mode
retrieval_mode
retrieval_limit
retrieved_chunk_count
unique_file_count
evidence_ids[]
latency_ms_total
latency_ms_retrieval
latency_ms_model
model_usage[]
total_estimated_cost_usd
insufficient_evidence
error_type
error_message
tool_call_count
```

`model_usage[]` fields:

```text
provider
model
input_tokens
output_tokens
total_tokens
cached_input_tokens
reasoning_tokens
estimated_cost_usd
pricing_source
pricing_version
```

Cost fields are telemetry only. They may be null when pricing is unknown,
pricing is deliberately disabled, or provider usage metadata is inconsistent.
The UI must not present null cost as zero.

## Lovable Build Brief

Build a quiet, utilitarian React TypeScript app for testing Repo Deep Research.
The app should feel like a focused developer tool: dense, scannable, and
work-oriented.

Primary layout:

- app shell with persistent product header and compact navigation;
- left or top query panel with controls;
- main answer area;
- right or lower evidence and trace panels;
- responsive layout that works on desktop and mobile.

Navigation:

- Research: active M3.6 direct-RAG testing view;
- Evaluations: disabled or placeholder route labeled as planned;
- Monitoring: disabled or placeholder route labeled as planned;
- Feedback: disabled or placeholder route labeled as planned;
- Settings: minimal local API configuration, or planned if configuration lives
  in the research view.

Backoffice placeholders should be quiet and clearly non-functional. They should
not contain fake charts, fake eval results, or invented operational data.

Controls:

- question textarea;
- mode segmented control: Auto, Locate, Flow, Change;
- retrieval mode segmented control: Dense, Sparse, Hybrid;
- limit numeric stepper or slider from 1 to 20;
- API base URL input, defaulting to `http://localhost:8000`;
- optional advanced repository path input;
- submit button with loading state.

Result views:

- answer summary;
- implementation flow list;
- relevant files;
- relevant symbols;
- change targets, shown only when present;
- risks;
- unresolved questions;
- insufficient-evidence state;
- evidence list with path, line range, symbol, score, reason, and evidence ID;
- trace/debug panel showing request ID, repository name, branch, commit hash,
  retrieval mode, retrieved chunk count, unique file count, latency, token usage,
  estimated cost when known, and tool-call count;
- raw JSON collapsible panel for debugging.

Interaction behavior:

- disable submit while a request is running;
- allow Enter with modifier key to submit from the textarea;
- show HTTP/network errors in a clear error area;
- show backend validation errors without stack traces;
- preserve the last successful result while a new request is loading;
- allow copying evidence paths and raw JSON;
- do not require authentication.

Visual design:

- use a restrained neutral base with one or two accent colors, not a one-hue
  palette;
- use compact panels and tables/lists instead of large decorative cards;
- keep cards at 8px radius or less;
- avoid hero sections, marketing copy, decorative gradients, or placeholder
  illustrations;
- use icons for submit, copy, expand/collapse, and settings where available;
- ensure long paths and symbols wrap or truncate cleanly without overlapping.

## Non-goals

Do not add:

- feedback persistence;
- telemetry database writes;
- Logfire dashboards;
- evaluation execution UI;
- monitoring charts;
- backoffice data tables;
- authentication;
- repository ingestion UI;
- agentic research UI beyond the current `POST /rag` contract;
- fake answers or mocked backend data as the primary experience;
- frontend-side retrieval or answer-generation logic.

## Suggested File Shape

Let Lovable choose the exact frontend scaffold, but keep these logical
components:

```text
App
AppShell
Navigation
RagQueryForm
AnswerPanel
EvidencePanel
TracePanel
RawJsonPanel
ApiError
PlannedBackofficePanel
```

Keep API types explicit in TypeScript. The UI should be a client of the backend
contract, not a second implementation of RAG logic.

## Acceptance Criteria

M3.6 is complete when:

- the user can submit a question to `POST /rag` from the browser;
- mode, retrieval mode, limit, and API base URL are controllable;
- `answer` and `trace` are both rendered clearly;
- evidence paths, symbols, line ranges, scores, and reasons are visible;
- null cost is shown as unknown or unavailable, not zero;
- loading, success, insufficient-evidence, validation-error, and network-error
  states are implemented;
- raw JSON can be inspected for debugging;
- the app shell leaves obvious room for future Evaluations, Feedback, and
  Settings areas without implementing their data flows;
- Monitoring shows the latest browser-local `RagRunResult` outcome, retrieval,
  latency, token usage, and cost metadata without backend persistence or
  invented historical data;
- the app runs locally with documented commands;
- no feedback, backend persistence, Logfire, evaluation execution, historical
  monitoring charts, authentication, or ingestion UI is added.

## Implementation Notes

- The Lovable-generated TanStack Start / React TypeScript project is vendored
  under `frontend/`, not kept as a nested Git checkout.
- The UI posts to the configured API base URL plus `/rag` and renders the
  M3.5 `RagRunResult` envelope.
- `change_targets[]` render as grounded objects with path, optional symbol,
  reason, and evidence IDs.
- `trace.model_usage[]` renders as a list of model calls, and cost fields accept
  either numeric values or stringified decimals.
- FastAPI allows configured local browser origins through
  `RDR_CORS_ALLOWED_ORIGINS` so the frontend can call `/rag` during local
  development; the runtime default is empty, so CORS is opt-in.
- Evaluations, Feedback, and Settings routes remain placeholder backoffice
  surfaces with no fake charts, persisted data, or operational workflows.
- Monitoring is a lightweight latest-run view sourced from the browser-local
  response JSON already produced by the Research route.

## Validation

Before considering the frontend ready:

```bash
make frontend-install
make frontend-test
make frontend-typecheck
make frontend-build
make api
```

Then run the frontend locally and submit:

```text
where is repository configuration validated?
```

Expected behavior:

- the request reaches `POST /rag`;
- the rendered output includes an answer area and trace/debug metadata;
- evidence appears with repository path and line-range metadata;
- the UI remains usable when `total_estimated_cost_usd` is null.
