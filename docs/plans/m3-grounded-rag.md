# M3 — Grounded direct RAG

## Goal

Provide a real backend slice that answers repository questions with structured,
application-validated citations, while leaving bounded agentic tool loops for
M4.

## Scope

- direct RAG over the existing `RepositoryDatabase.search` boundary;
- typed research requests, answers, evidence, change targets, and judge results;
- opaque evidence IDs mapped back to canonical chunk paths and line ranges;
- deterministic insufficient-evidence behavior when retrieval or citation
  validation fails;
- OpenAI Responses API adapter with `gpt-5-mini` for answers and `gpt-5.1` for
  opt-in judge evaluation;
- CLI commands for `research` and `evaluate-answers`;
- minimal FastAPI `/health` and `/research` endpoints for future React/Lovable
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

- research service maps evidence IDs to canonical citations;
- unknown evidence IDs and empty retrieval return insufficient evidence;
- answer-evaluation reports write stable JSON;
- CLI parses and emits M3 research output with fake adapters;
- FastAPI `/health` and `/research` return stable contract shapes.

## Outcome

Completed on 2026-07-27.

- `ResearchService` now generates direct-RAG answers from retrieved chunks and
  validates all citations before returning a `ResearchAnswer`.
- `OpenAIResponsesModel` provides the live answer and judge adapter behind a
  small protocol used by tests and services.
- `repo-research research` and `repo-research evaluate-answers` expose the M3
  backend through CLI JSON commands.
- `repo_research.api:create_app` exposes `/health` and `/research` with
  injectable dependencies for tests and future UI integration.

## Validation

Completed locally:

- `make lint` — passed;
- `make typecheck` — passed (strict mypy, 18 source files);
- `make test` — passed (30 tests);
- `make docker-up` — passed; Qdrant reported healthy;
- `make ingest-self` — passed (351 chunks, no skipped files).

Skipped locally:

- live `repo-research research ...` smoke test — `OPENAI_API_KEY` was not set;
- live `repo-research evaluate-answers ...` smoke test — `OPENAI_API_KEY` was
  not set.
