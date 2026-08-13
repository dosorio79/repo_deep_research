# Capstone follow-up release plan

## Summary

`v0.5.7` makes monitoring and evaluation visible and inspectable with
PostgreSQL-backed dashboards. The next release should be the first user-ready
Local Alpha, not a new product-feature release.

Highest priorities:

1. Local Alpha runbook for a technical user.
2. User-facing screenshots and examples.
3. Known limitations and a concise local BYOK validation path.

## v0.5.6: Monitoring charts

Goal: turn the PostgreSQL-backed monitoring page from cards and tables into a
dashboard with at least five useful charts.

Status: released to `main` as `v0.5.6`.

Requirements from the PRD:

- Requests over time.
- End-to-end latency.
- Retrieval latency.
- Token usage or estimated cost.
- Positive feedback rate.
- Error rate.
- Average tool calls per research request.

Implementation approach:

- Keep PostgreSQL as the user-visible monitoring source of truth.
- Use existing `GET /monitoring/runs` and `GET /monitoring/runs/{request_id}`
  data where possible.
- Use the existing Recharts dependency for line/bar charts.
- Put recent runs near the top of `/monitoring` so operators start from the
  inspectable run history.
- Feed the cards and charts from the same scoped loaded-run set.
- Add an explicit dashboard scope toolbar with kind/status/feedback/limit chips
  and date slicers: all loaded, newest 24h, newest 7d, and newest 30d.
- Keep row selection inspect-only by opening run detail in a sheet; selecting a
  row does not filter cards or charts.
- Keep all-time PostgreSQL summary panels, but label them separately from the
  current dashboard scope.

Acceptance checks:

- `/monitoring` shows at least five real chart panels when persisted run rows
  exist.
- Empty states remain honest when no run rows exist.
- Tests cover chart rendering from representative direct and agentic run data.
- Tests cover scoped cards/charts, run-first layout order, date slicing, and
  selected run detail in a sheet.
- `make test-all` passes.
- `make compose-up` passes.
- README/setup docs explain how to produce a monitoring screenshot.

Implemented chart panels:

- Runs over time.
- Latency by mode.
- Retrieval volume.
- Estimated cost by mode.
- Feedback mix.
- Errors and tool calls.

Current validation evidence:

- `npm test -- src/routes/-monitoring.test.tsx`: passed.
- `npm run typecheck`: passed.
- `npm run lint`: passed with existing Fast Refresh warnings in shared UI
  primitives.
- Playwright visual check on the branch build confirmed desktop/mobile order,
  the detail sheet interaction, and no page-level horizontal overflow at 390px.

Out of scope:

- Grafana.
- Making Logfire mandatory.
- Storing prompts, answers, or source-code excerpts solely for charting.

## v0.5.7: Evaluation workbench

Goal: publish defensible evaluation evidence for retrieval and answer quality,
including both curated datasets and real monitored answers.

Status: released to `main` as `v0.5.7`.

The work landed in three slices so the storage contract arrived before runner
and UI behavior:

- `v0.5.7a`: PostgreSQL persistence foundation for answer snapshots,
  evaluation runs, and evaluation results.
- `v0.5.7b`: unified evaluation runner for dataset and monitored-run sources.
- `v0.5.7c`: user-visible `/evaluations` dashboard backed by persisted
  evaluation results.

### v0.5.7a: Evaluation persistence foundation

Status: released in `v0.5.7`.

Scope:

- Persist answer snapshots for completed `/rag` and `/research` runs when
  telemetry persistence is configured.
- Store answer JSON and citation metadata, not full retrieved source excerpts.
- Add PostgreSQL tables for evaluation batch metadata and per-answer judge
  results.
- Keep the existing monitoring dashboard APIs unchanged.
- Keep evaluation execution and `/evaluations` UI out of this slice.

Acceptance checks:

- `monitoring_runs`, `feedback_events`, `answer_snapshots`,
  `evaluation_runs`, and `evaluation_results` are initialized together.
- Direct API runs persist both monitoring trace metadata and an answer snapshot.
- Agentic snapshot construction is covered without relying on the currently
  fragile ASGI `/research` test boundary.
- Focused recording-store and API tests pass.

### v0.5.7b: Unified evaluation runner

Status: released in `v0.5.7`.

Retrieval evaluation:

- Confirm `eval/development.json` and `eval/held_out.json` jointly satisfy the
  30-question requirement.
- Confirm question distribution: locate, flow, and change-impact.
- Run held-out retrieval evaluation for dense, sparse, and hybrid modes.
- Summarize Hit Rate@k, MRR, Recall@k, Precision@k, file-level hit rate, and
  symbol-level hit rate in `docs/evaluation.md`.
- Update README with the final retrieval choice and measured metrics.

Answer evaluation:

- Compare direct RAG baseline against bounded agentic research.
- Evaluate persisted monitored answers from `answer_snapshots` without
  regenerating answers.
- Persist evaluation-run lifecycle and per-answer judge results to PostgreSQL
  when `--persist` is supplied.
- Keep dataset evaluation results linked by `record_id`; only monitored-run
  evaluation results should set `request_id` because that column references
  `answer_snapshots`.
- Use a small but explicit reviewed dataset first if full live evaluation is too
  slow or costly.
- Report correctness, groundedness, citation accuracy, completeness,
  usefulness, and unsupported-claim rate.
- Keep live OpenAI judging opt-in.
- Persist summarized results in docs for users; avoid committing raw
  generated noise unless intentionally curated.

Acceptance checks:

- Evaluation commands are documented and copy-pasteable.
- `evaluate-answers --source dataset --approach both` produces direct and
  agentic result rows.
- `evaluate-answers --source monitored-runs --persist` reads answer snapshots
  and writes `evaluation_runs` plus `evaluation_results`.
- Final retrieval metrics are visible in `docs/evaluation.md` and README.
- Direct-vs-agentic answer evaluation summary is visible in docs and README.
- Generated outputs remain ignored unless intentionally promoted to a stable
  summary artifact.

### v0.5.7c: Evaluation dashboard

Goal: make evaluation inspectable from the browser rather than only from CLI
JSON output.

Status: released in `v0.5.7`.

Dashboard panels:

- Average score by approach: direct versus agentic.
- Score distribution by metric.
- Unsupported-claim rate by approach.
- Feedback useful/not-useful compared with judge scores.
- Quality compared with latency and estimated cost.
- Worst-scoring evaluated answers for user inspection.

Acceptance checks:

- `/evaluations` renders honest empty states before evaluation results exist.
- Persisted evaluation results produce real summary cards, charts, and an
  inspectable result table.
- Frontend tests cover empty and populated states.

## v0.5.8: Local Alpha

Goal: make the project usable and understandable as a local-first alpha for
technical users who bring their own OpenAI API key.

Positioning:

- Local-only deployment.
- BYOK through `.env.local`.
- Docker Compose for frontend, API, Qdrant, and PostgreSQL.
- Local Python repository ingestion.
- No free hosted deployment target for this alpha.

Required deliverables:

- README Local Alpha section.
- Stack diagram linked from README.
- Monitoring dashboard screenshot.
- Evaluation dashboard screenshot.
- Research UI screenshot.
- Example direct RAG output.
- Example agentic research output.
- Dataset/corpus description.
- Final retrieval and answer-evaluation summaries.
- Known limitations.
- Complete local user runbook using Docker Compose.
- Optional short preview video notes or script.

Acceptance checks:

- A user can clone, configure, start, ingest, query, inspect monitoring, and
  find evaluation evidence using only README and linked docs.
- README maps major product capabilities to concrete files, commands,
  screenshots, or examples.
- The release explicitly states that hosted deployment, multi-tenant auth, and
  managed cloud persistence are out of scope for the Local Alpha.

## Logfire Position

Logfire is useful optional APM/tracing for FastAPI and PydanticAI. It should
remain enabled by configuration only. It is not the primary user dashboard for
the capstone because the user-visible evidence is backed by PostgreSQL and
rendered locally in `/monitoring`.

Do not spend the next release on Logfire unless PostgreSQL-backed monitoring
cannot satisfy a user-visible evidence requirement.
