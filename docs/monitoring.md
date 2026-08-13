# Monitoring KPIs

The `/monitoring` route is a local admin/operator dashboard backed by
PostgreSQL. It summarizes persisted `/rag` and `/research` runs, linked
feedback, token/cost telemetry, and failures. It is not Logfire and does not
depend on external tracing.

## Data Sources

| Source | Written by | Used for |
|---|---|---|
| `monitoring_runs` | Completed direct and agentic API runs. | Run history, latency, retrieval volume, errors, model usage, and cost. |
| `feedback_events` | Browser feedback submissions. | Useful/not-useful counts linked by `request_id` or session. |
| `answer_snapshots` | Completed answers persisted for later judging. | Monitored-answer evaluation; not directly charted on `/monitoring`. |

When PostgreSQL is not configured, the application uses `NoOpRecordingStore` and
the monitoring dashboard shows honest empty states.

## Dashboard Scopes

The top cards and charts use the currently loaded run list after filters:

- kind: all, direct, or agentic;
- status: all, no error, or error;
- feedback: all, useful, not useful, or none;
- date range: all loaded, newest 24h, newest 7d, or newest 30d;
- limit: 25, 50, or 100 recent runs.

Date ranges are anchored to the newest loaded run timestamp, not wall-clock
time, so sample data remains inspectable even when it is older than today.

The "All-time persisted summary" panels use aggregate backend data independent
of the current dashboard filters.

## KPI Definitions

| KPI | Definition | Source fields |
|---|---|---|
| Runs | Count of loaded runs in scope, split by direct and agentic. | `run_kind` |
| Latency | Average end-to-end run latency for scoped runs. Retrieval average is shown separately. | `latency_ms_total`, `latency_ms_retrieval` |
| Retrieval | Total retrieved chunks and unique files across scoped runs. | `retrieved_chunk_count`, `unique_file_count` |
| Cost | Sum of known estimated OpenAI costs for scoped runs. Unknown costs are omitted and shown as unavailable where no cost exists. | `total_estimated_cost_usd` |
| Feedback | Count of useful and not-useful feedback events linked to scoped runs. | `feedback_useful`, `feedback_not_useful` |
| Errors | Count of scoped runs with an error. Error-type breakdown appears in the all-time panels. | `has_error`, `error_type` |
| Runs over time | Direct and agentic run counts grouped by completion timestamp bucket. | `completed_at`, `run_kind` |
| Latency by mode | Average total and retrieval latency for direct versus agentic runs. | `run_kind`, `latency_ms_total`, `latency_ms_retrieval` |
| Retrieval volume chart | Retrieved chunks and unique files by recent run. | `retrieved_chunk_count`, `unique_file_count` |
| Estimated cost by mode | Sum of known estimated costs by direct versus agentic runs. | `run_kind`, `total_estimated_cost_usd` |
| Feedback mix | Useful versus not-useful linked feedback count and positive feedback rate. | `feedback_useful`, `feedback_not_useful` |
| Errors and tool calls | Error count and average agentic tool calls for the selected scope. | `has_error`, `tool_call_count`, `run_kind` |

## Interpretation Rules

- Monitoring is operational telemetry for the locally running product, not a
  model-quality benchmark.
- Retrieval counts show how much evidence was returned, not whether the evidence
  was correct. Use evaluation metrics for quality.
- Cost is estimated from provider usage metadata and configured pricing. If any
  model call has unknown pricing, the run cost may be unavailable.
- Feedback is user/operator feedback, not judge scoring. It is useful for
  spotting bad experiences and choosing monitored answers for later evaluation.
- Agentic tool-call averages apply to agentic runs; direct RAG normally has zero
  tool calls.

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /monitoring/summary` | Aggregate persisted monitoring panels. |
| `GET /monitoring/runs` | Recent run list with kind, repository, error, feedback, and limit filters. |
| `GET /monitoring/runs/{request_id}` | One run detail with metadata, model usage, and linked feedback. |
