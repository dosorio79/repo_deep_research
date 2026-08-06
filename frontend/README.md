# Repo Deep Research Frontend

React TypeScript frontend testing harness for Repo Deep Research M3.6.

Purpose: a course/capstone reviewer demo for an existing FastAPI backend. The first screen is a polished single-page research flow for ingestion, question asking, grounded answers, and evidence. The technical console remains available at `/backoffice`.

Backend: POST to http://localhost:8000/repositories/ingest before research, then POST to http://localhost:8000/rag or http://localhost:8000/research. Ingestion request fields: repository_address string, accepting a local path or public GitHub URL. Direct RAG request fields: question string, mode one of auto/locate/flow/change, retrieval_mode one of dense/sparse/hybrid, limit 1-20, optional repository_path. Agentic RAG uses retrieval_limit instead of limit. API base URL must be editable and default to http://localhost:8000.

Response: RagRunResult with { answer, trace }. Render both clearly. answer includes summary, implementation_flow, evidence, relevant_files, relevant_symbols, change_targets, risks, confidence, unresolved_questions, insufficient_evidence. Evidence includes evidence_id, path, start_line, end_line, symbol, score, reason. trace includes request_id, repository_name, branch, commit_hash, question_mode, retrieval_mode, retrieval_limit, retrieved_chunk_count, unique_file_count, latency_ms_total, latency_ms_retrieval, latency_ms_model, model_usage, total_estimated_cost_usd, insufficient_evidence, error_type, error_message, tool_call_count. model_usage includes token counts and estimated_cost_usd.

Cost fields are telemetry only. If null, show Unknown or Unavailable, never zero.

Layout: compact app shell with persistent header and navigation. Navigation entries: Research active and Monitoring active for the latest browser-local RAG response. The denser technical console remains reachable at `/backoffice` without being promoted in the primary nav. Future Evaluation, Feedback, and full observability slices must contain no fake charts, fake evals, or invented operational data.

Research view controls: repository address input, ingest button with loading state, question textarea, suggested reviewer questions, direct RAG / agentic RAG segmented control, mode segmented control, retrieval mode segmented control, limit slider, API base URL input, submit button with loading state. The Backoffice route keeps the denser technical control surface.

Results: answer summary, implementation flow, relevant files/symbols, change targets only if present, risks, unresolved questions, insufficient-evidence state, evidence highlights, and compact run metadata. Preserve last successful result while loading and when navigating to Monitoring and back. Show network/backend validation errors clearly without stack traces. Keep full trace/debug panels and raw JSON in Monitoring or `/backoffice`. Support Cmd/Ctrl+Enter submit.

Visual style: reviewer-facing GenAI application, simple and efficient but more polished than a Streamlit-style harness. Prioritize a clear composer, evidence-first answer cards, restrained neutral surfaces, one or two accents, compact panels, radius 8px or less, no decorative gradients, no fake data. Use icons where appropriate. Long paths must wrap/truncate cleanly.

Suggested components: App, AppShell, Navigation, RepositoryIngestPanel, RagQueryForm, AnswerPanel, EvidencePanel, TracePanel, RawJsonPanel, ApiError, PlannedBackofficePanel. Keep explicit TypeScript API types. No auth, no backend persistence, no Logfire, no evaluation execution UI, no historical monitoring charts, no frontend RAG logic.

This frontend is vendored into the main `repo_deep_research` repository under
`frontend/`.

## Development

You need Node.js and npm. From the repository root:

```sh
make frontend-install
make api
make frontend-dev
```

Or run commands directly from this directory:

```sh
npm install
npm test
npm run typecheck
npm run build
npm run dev
```
