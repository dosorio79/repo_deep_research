# M3 — Grounded direct RAG

## Goal

Provide a real backend slice that answers repository questions with structured,
application-validated citations, while leaving bounded agentic tool loops for
M4.

## Scope

- direct RAG over the existing `RepositoryDatabase.search` boundary;
- typed RAG requests, answers, evidence, change targets, and judge results;
- opaque evidence IDs mapped back to canonical chunk paths and line ranges;
- deterministic insufficient-evidence behavior when retrieval or citation
  validation fails;
- OpenAI Responses API adapter with `gpt-5-mini` for answers and `gpt-5.1` for
  opt-in judge evaluation;
- CLI commands for `rag` and `evaluate-answers`;
- minimal FastAPI `/health` and `/rag` endpoints for future React/Lovable
  frontend integration.

## Decisions

- Keep M3 as direct RAG only. PydanticAI tool loops, follow-up searches, and
  agentic change-impact planning remain M4.
- Let models cite evidence IDs only; application code owns paths, symbols, line
  ranges, and citation validation.
- Keep default tests offline with fake model adapters. Live answer generation
  and judging require `OPENAI_API_KEY`.
- Include the minimal FastAPI surface now so later UI work has a backend target,
  but defer feedback, Logfire, dashboards, and frontend work.

## Affected tests

- direct-RAG service maps evidence IDs to canonical citations;
- unknown evidence IDs and empty retrieval return insufficient evidence;
- answer-evaluation reports write stable JSON;
- CLI parses and emits M3 direct-RAG output with fake adapters;
- FastAPI `/health` and `/rag` return stable contract shapes.

## Outcome

Completed on 2026-07-27.

- `DirectRagService` now generates direct-RAG answers from retrieved chunks and
  validates all citations before returning a `RagAnswer`.
- `OpenAIResponsesModel` provides the live answer and judge adapter behind a
  small protocol used by tests and services.
- `repo-research rag` and `repo-research evaluate-answers` expose the M3
  backend through CLI JSON commands.
- `repo_research.api:create_app` exposes `/health` and `/rag` with
  injectable dependencies for tests and future UI integration.

## Cleanup before M4

Completed after the adversarial clarity review:

- moved runtime composition into `runtime.py` so CLI and FastAPI share backend
  construction without API importing CLI internals;
- kept the CLI as a first-class entry point while making FastAPI the future
  frontend-facing consumer of the same service;
- removed the hidden answer-context path weighting so direct RAG preserves the
  selected retrieval mode's result order;
- kept evaluation responsible for selecting the default retrieval mode, while
  CLI/API callers can still choose dense, sparse, or hybrid per request;
- introduced clearer grouped env names for answer model and limits while
  preserving legacy local `.env` aliases;
- changed API contract tests to use an async ASGI transport and async route
  functions, avoiding the local Starlette `TestClient`/AnyIO threadpool hang.

This cleanup does not start M4. The next milestone remains bounded agentic
research over the same backend and retrieval contracts.

Terminology cleanup before M4:

- renamed the current M3 module from `research.py` to `rag.py`;
- renamed the direct-RAG service and boundary models to `DirectRagService`,
  `RagRequest`, `RagAnswer`, and `RagMode`;
- renamed the public M3 command and API endpoint to `repo-research rag` and
  `POST /rag`;
- reserved "research" for the future M4 agentic investigation workflow.

Live smoke hardening before M4:

- added deterministic mode inference so common "where is" questions run as
  locate answers even when the request uses auto mode;
- tightened direct-RAG prompt rules so locate/flow answers do not emit change
  targets and do not ask whether the user wants paths or citations already
  returned by the application;
- added deterministic post-generation cleanup that removes change targets
  outside change mode and drops metadata-preference unresolved questions while
  preserving real evidence gaps.

Cleanup validation completed locally:

- `uv run ruff check src tests scripts` — passed;
- `uv run ruff format --check src tests scripts` — passed;
- `uv run mypy` — passed (strict mypy, 19 source files);
- `uv run pytest` — passed (40 tests).

## Validation

Completed locally:

- `make lint` — passed;
- `make typecheck` — passed (strict mypy, 18 source files);
- `make test` — passed (30 tests);
- `make docker-up` — passed; Qdrant reported healthy;
- `make ingest-self` — passed (351 chunks, no skipped files).

Skipped locally:

- live `repo-research rag ...` smoke test — `OPENAI_API_KEY` was not set;
- live `repo-research evaluate-answers ...` smoke test — `OPENAI_API_KEY` was
  not set.
