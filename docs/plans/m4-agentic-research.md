# M4 - Agentic Deep Research

## Goal

Add the first bounded agentic research slice that can produce an
evidence-backed change-impact plan for this repository.

The M4 workflow builds on the M3 direct-RAG retrieval and citation contracts and
reuses the M3.5 answer-plus-trace response pattern for tool-call counts, latency,
model usage, and estimated cost. M4 still reserves "research" for a tool-using
investigation flow with follow-up searches and explicit tool-call bounds.

## First branch scope

Branch: `feat/m4-agentic-research-tools`

This branch should deliver the smallest useful vertical slice:

- typed research request, answer, dependency, and budget models;
- a fakeable research service that enforces search, file-read, and total
  tool-call limits in application code;
- configurable defaults for maximum searches, file reads, and total tool calls;
- bounded `search_repository`, `read_chunk`, `read_file`, and `find_symbol`
  tools over the requested repository revision;
- structured change-impact output grounded in retrieved or read repository
  evidence;
- a `ResearchRunResult` response envelope that follows the M3.5 trace contract;
- a CLI command for local reviewer smoke testing;
- focused offline tests using fake model/tool dependencies.

## Non-goals

This branch must not add:

- automatic code changes or pull request creation;
- multi-agent orchestration;
- compiler-grade static analysis;
- frontend work;
- feedback persistence;
- Logfire instrumentation;
- monitoring dashboards;
- new language support;
- broad API expansion beyond what is needed for the M4 slice.

## Proposed implementation order

1. Add typed M4 request, answer, and budget models.
2. Add tests for budget validation and grounded change-target shape.
3. Implement the deterministic research service around fakeable protocols.
4. Add configurable budget defaults in the central settings model.
5. Add bounded repository tools over the existing search boundary, chunk reads,
   safe repository file reads, and symbol lookup.
6. Add the live PydanticAI adapter behind the same service boundary.
7. Return the M3.5-style response envelope with agentic trace metadata.
8. Add the CLI command and README usage notes.
9. Run narrow tests first, then the standard validation commands.

## Acceptance criteria

The first M4 slice is complete when the system can answer a self-repository
change question with:

- a useful summary;
- implementation flow notes;
- cited evidence with valid paths and line ranges;
- change targets with reasons and evidence IDs;
- clear risks and unresolved questions;
- enforced tool-call bounds;
- trace metadata with tool-call count, latency, model usage, and estimated cost
  where available;
- no unrestricted shell access;
- default tests that do not require paid model calls.

## Affected tests

Expected test coverage for the implementation branch:

- model validation for research requests, answers, and budget limits;
- tool budget enforcement for searches, file reads, and total calls;
- configurable budget defaults are loaded and validated;
- repository file reads cannot escape the requested repository root;
- search tool returns the same typed evidence shape as existing retrieval;
- chunk and symbol tools return only evidence from the requested repository
  revision;
- final answers cannot cite unread or unretrieved evidence;
- response trace reports bounded tool calls and model usage without requiring
  paid model calls in default tests;
- CLI parses and emits the M4 structured response with fake dependencies.

## Validation

Use the shared writable uv cache when running local checks:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make lint
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make typecheck
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache make test
```

Run integration checks only after storage, API, or live agent boundaries are
changed.

## Status

Deferred until M3.5 is complete.
