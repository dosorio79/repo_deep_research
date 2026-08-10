# Capstone follow-up release plan

## Summary

`v0.5.5` makes monitoring visible and inspectable, but the remaining capstone
evidence work is not finished. The next releases should focus on reviewer
scoring evidence, not new product surface area.

Highest priorities:

1. Monitoring graphs that satisfy the dashboard rubric.
2. Final retrieval and answer-evaluation evidence.
3. Reviewer packaging: screenshots, examples, README rubric map, and runbook.

## v0.5.6: Monitoring charts

Goal: turn the PostgreSQL-backed monitoring page from cards and tables into a
dashboard with at least five useful charts.

Status: in progress on `feat/mvp-monitoring-charts`.

Requirements from the PRD:

- Requests over time.
- End-to-end latency.
- Retrieval latency.
- Token usage or estimated cost.
- Positive feedback rate.
- Error rate.
- Average tool calls per research request.

Implementation approach:

- Keep PostgreSQL as the reviewer-visible monitoring source of truth.
- Use existing `GET /monitoring/runs` and `GET /monitoring/runs/{request_id}`
  data where possible.
- Use the existing Recharts dependency for line/bar charts.
- Keep current summary cards, recent run table, filters, and detail panel.
- Add chart panels below the summary cards and above or beside the run table.
- Add time-window or limit controls only if the existing `limit` filter is not
  enough for readable charts.

Acceptance checks:

- `/monitoring` shows at least five real chart panels when persisted run rows
  exist.
- Empty states remain honest when no run rows exist.
- Tests cover chart rendering from representative direct and agentic run data.
- `make test-all` passes.
- `make compose-up` passes.
- README/setup docs explain how to produce a monitoring screenshot.

Out of scope:

- Grafana.
- Making Logfire mandatory.
- Storing prompts, answers, or source-code excerpts solely for charting.

## v0.5.7: Evaluation finalization

Goal: publish defensible evaluation evidence for retrieval and answer quality.

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
- Use a small but explicit reviewed dataset first if full live evaluation is too
  slow or costly.
- Report correctness, groundedness, citation accuracy, completeness,
  usefulness, and unsupported-claim rate.
- Keep live OpenAI judging opt-in.
- Persist summarized results in docs for reviewers; avoid committing raw
  generated noise unless intentionally curated.

Acceptance checks:

- Evaluation commands are documented and copy-pasteable.
- Final retrieval metrics are visible in `docs/evaluation.md` and README.
- Direct-vs-agentic answer evaluation summary is visible in docs and README.
- Generated outputs remain ignored unless intentionally promoted to a stable
  summary artifact.

## v0.5.8: Reviewer packaging

Goal: make the project easy to score without requiring the reviewer to infer
where evidence lives.

Required packaging:

- README rubric map.
- Monitoring dashboard screenshot.
- Research UI screenshot.
- Example direct RAG output.
- Example agentic research output.
- Dataset/corpus description.
- Final retrieval and answer-evaluation summaries.
- Known limitations.
- Complete local runbook using Docker Compose.
- Optional short preview video notes or script.

Acceptance checks:

- A reviewer can clone, configure, start, ingest, query, inspect monitoring, and
  find evaluation evidence using only README and linked docs.
- README maps every major scoring criterion to concrete files, commands, or
  screenshots.

## Logfire Position

Logfire is useful optional APM/tracing for FastAPI and PydanticAI. It should
remain enabled by configuration only. It is not the primary reviewer dashboard
for the capstone because the reviewer-visible evidence is backed by PostgreSQL
and rendered locally in `/monitoring`.

Do not spend the next release on Logfire unless PostgreSQL-backed monitoring
cannot satisfy a rubric requirement.
