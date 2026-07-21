# AGENTS.md

## Mission

Build **Repo Deep Research**, a focused LLM Zoomcamp capstone that investigates Python repositories using agentic RAG.

The system must answer:

1. where implementation logic lives;
2. how logic flows across modules;
3. which files, symbols, configuration, and tests may need changes for a requested adaptation.

Answers must be grounded in repository evidence with valid paths, symbols, and line ranges.

Read `PRD.md` before making architectural or product decisions.

## Product constraints

- Python repositories are the primary scope.
- Use one research agent, not a multi-agent system.
- Do not implement automatic code changes or pull requests.
- Do not build compiler-grade static analysis.
- Do not add support for additional languages unless explicitly requested.
- Do not add infrastructure that is not required by the current milestone.
- Prefer the smallest implementation that satisfies the relevant acceptance criteria.
- Preserve a clear distinction between verified repository facts and recommended changes.
- The application must be able to ingest and research its own repository.

## Delivery strategy

Work milestone by milestone in the order defined in `PRD.md`.

Do not start later milestones while an earlier milestone lacks its exit condition.

For tasks that span multiple modules or require significant design decisions:

1. inspect the relevant code and documentation;
2. write or update an implementation plan in `docs/plans/`;
3. identify affected tests;
4. implement the smallest complete vertical slice;
5. run required validation;
6. update documentation.

Avoid broad scaffolding that contains placeholders without a working path.

## Expected repository layout

```text
.
├── AGENTS.md
├── PRD.md
├── README.md
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── .env.example
├── src/
│   └── repo_research/
│       ├── api/
│       ├── agent/
│       ├── ingestion/
│       ├── retrieval/
│       ├── storage/
│       ├── evaluation/
│       ├── monitoring/
│       ├── config.py
│       └── cli.py
├── app/
├── eval/
├── tests/
└── docs/
    ├── architecture.md
    ├── evaluation.md
    ├── setup.md
    ├── usage.md
    ├── decisions/
    └── plans/
```

Adapt this structure only when there is a concrete simplification or implementation need. Do not create empty modules solely to match the proposed tree.

## Technology defaults

Use these unless the current code or an accepted architecture decision says otherwise:

- Python 3.12
- `uv` for dependency and environment management
- Pydantic v2 for models and validation
- PydanticAI for the research agent
- Qdrant for dense and sparse retrieval
- FastAPI for the API
- Streamlit for the minimal UI
- Logfire for tracing and monitoring
- SQLite for initial feedback persistence
- pytest for testing
- Ruff for linting and formatting
- mypy or Pyright for static type checking
- Docker Compose for the complete runnable stack

Do not add a production dependency without explaining why the standard library or an existing dependency is insufficient.

## Engineering conventions

### Python

- Use type annotations for public functions, methods, and models.
- Prefer small, explicit modules over generic utility files.
- Use Pydantic models at system boundaries.
- Prefer dependency injection over module-level mutable clients.
- Keep business logic independent from FastAPI and Streamlit.
- Avoid hidden global state.
- Use `pathlib.Path` for filesystem paths.
- Use structured logging and tracing rather than `print`.
- Raise domain-specific exceptions where callers can recover.
- Include useful error context without exposing secrets.
- Do not catch `Exception` unless re-raising with context or handling at an application boundary.

### Async behavior

- Use async APIs consistently in request and agent paths.
- Do not introduce async wrappers around CPU-bound parsing without a measured need.
- Keep ingestion orchestration separate from request-time research.

### Configuration

- Centralize runtime configuration in `src/repo_research/config.py`.
- Load secrets and environment-specific values from environment variables.
- Keep `.env.example` complete and non-secret.
- Do not hard-code model names, collection names, URLs, limits, or credentials in business logic.
- Validate configuration at startup.

### Models

Use explicit models for at least:

- repository identity;
- parsed chunk;
- search query;
- search result;
- evidence;
- research answer;
- change target;
- feedback event;
- evaluation record;
- evaluation result.

Avoid passing untyped dictionaries across module boundaries.

## Repository ingestion rules

- Respect `.gitignore` where practical.
- Always ignore `.git`, virtual environments, caches, build outputs, binary files, and generated artifacts.
- Make file-size limits configurable.
- Record repository name, branch, and commit hash.
- Use content hashes for idempotency.
- Associate indexed chunks with a specific commit.
- A repeated ingestion of the same commit must not duplicate points.
- Removed or superseded chunks must not appear as current results.

### Python parsing

Use `ast` before considering heavier parsers.

Extract:

- imports;
- top-level functions;
- classes;
- methods;
- decorators;
- signatures;
- docstrings;
- parent symbols;
- start and end lines.

Preserve enough surrounding context for retrieval without duplicating entire large files.

### Documentation and configuration

- Chunk Markdown by heading hierarchy.
- Keep small configuration files whole when that improves meaning.
- Split larger configuration files by logical top-level section.
- Preserve path, heading, and line metadata.

## Retrieval rules

Expose a common retrieval protocol or abstract interface.

Required modes:

- dense;
- sparse;
- hybrid.

Every mode returns the same typed `SearchResult` shape.

Search results must preserve:

- point or chunk ID;
- repository and commit;
- path;
- symbol;
- line range;
- chunk type;
- score;
- content or retrievable content reference.

### Hybrid search

Use Qdrant named vectors or the current recommended equivalent.

Use Reciprocal Rank Fusion as the initial hybrid baseline unless evaluation supports another fusion method.

Do not tune fusion weights without recording the experiment.

### Query rewriting

- Preserve the original user question.
- Make rewritten search queries observable in traces.
- Evaluate rewriting against a no-rewrite baseline.
- Avoid rewriting questions into assumptions not present in the request.

### Reranking

- Implement only after dense, sparse, and hybrid baselines work.
- Rerank a bounded candidate set.
- Keep reranking behind a configuration flag.
- Do not make it the default until evaluation demonstrates an improvement.

## Agent rules

Use one PydanticAI agent with typed dependencies and structured output.

Minimum tools:

- `search_repository`
- `read_chunk`
- `read_file`
- `find_symbol`

Optional tool:

- `find_references`

The agent must not receive unrestricted shell access as part of the application flow.

### Research bounds

Defaults:

- maximum searches: 3;
- maximum file reads: 5;
- maximum total tool calls: 8.

Keep these configurable and enforce them in code, not only in prompts.

### Grounding

The final answer must:

- cite valid paths and line ranges;
- identify symbols when available;
- separate evidence from inference;
- state uncertainty;
- avoid claims unsupported by retrieved content;
- never invent files, functions, classes, configuration, tests, or line numbers.

Before returning a final answer, validate that cited evidence refers to retrieved or read content.

### Structured output

The research output should include:

- `summary`
- `implementation_flow`
- `evidence`
- `change_targets`
- `risks`
- `confidence`
- `unresolved_questions`

Change-impact recommendations must explain why each file or symbol is relevant.

## API and UI rules

### FastAPI

- Keep routes thin.
- Validate requests and responses.
- Put orchestration in application services.
- Provide health endpoints for the app and required dependencies.
- Return stable error shapes.
- Do not expose stack traces or secrets.

### Streamlit

- Treat Streamlit as a client of the application service or API.
- Do not duplicate retrieval or agent logic in UI code.
- Display evidence clearly.
- Show repository and commit identity.
- Include useful/not-useful feedback.
- Make experimental retrieval controls optional and visually separate from the primary workflow.

## Evaluation requirements

Evaluation is a product feature, not an afterthought.

### Ground truth

Maintain evaluation records under `eval/`.

Each question should include:

- ID;
- question;
- question type;
- relevant files;
- relevant symbols where applicable;
- notes for human verification.

Split development and held-out records.

Do not modify the held-out set merely to improve reported metrics.

### Retrieval evaluation

Evaluate at least:

- dense;
- sparse;
- hybrid.

When implemented, also evaluate:

- query rewriting;
- reranking.

Report:

- Hit Rate@k;
- MRR;
- Recall@k;
- Precision@k;
- file-level Hit Rate;
- symbol-level Hit Rate.

Select the production retrieval configuration from results, not preference.

### LLM evaluation

Compare at least two answer-generation approaches:

- direct RAG baseline;
- bounded agentic research.

Evaluate:

- correctness;
- groundedness;
- citation accuracy;
- completeness;
- usefulness;
- unsupported claims.

Keep evaluation prompts, models, parameters, and result files versioned.

## Monitoring and feedback

Instrument:

- FastAPI requests;
- agent runs;
- tool calls;
- retrieval operations;
- model calls;
- errors.

Record at least:

- request ID;
- repository and commit;
- question type;
- retrieval mode;
- rewritten queries;
- retrieved chunk count;
- unique files;
- tool-call count;
- retrieval latency;
- model latency;
- total latency;
- token usage;
- estimated cost where applicable;
- errors;
- user feedback.

Never log secrets, authorization headers, complete environment values, or unnecessary private source content.

The final monitoring view must include at least five useful charts or panels to satisfy the project rubric.

Prefer Logfire alone if it can provide the required reviewer-visible dashboard. Add Grafana only through an explicit architecture decision.

## Tests

Every meaningful change must include or update tests.

Required categories:

### Unit tests

- ignore and filtering rules;
- AST extraction;
- line ranges;
- chunk IDs and content hashes;
- model validation;
- metric calculations;
- citation validation.

### Integration tests

- Qdrant indexing and retrieval;
- idempotent re-ingestion;
- dense, sparse, and hybrid result shape;
- agent tool boundaries;
- API request and response contracts;
- feedback persistence.

### Evaluation smoke tests

- evaluation dataset loads;
- each retrieval mode runs;
- metrics remain within valid ranges;
- output artifacts are written deterministically.

Use fixtures with small repository samples. Do not require paid model calls for the default unit-test suite.

## Commands

Prefer Make targets as the public developer interface.

Expected commands:

```bash
make install
make lint
make format
make typecheck
make test
make test-integration
make docker-up
make docker-down
make ingest-self
make evaluate-retrieval
make evaluate-answers
make api
make ui
```

When modifying code, run the narrowest relevant tests first, followed by the complete required validation for the milestone.

Before declaring a task complete, run:

```bash
make lint
make typecheck
make test
```

Run integration tests when storage, API, ingestion, or agent boundaries change.

## Documentation

Update documentation in the same change when behavior, configuration, commands, architecture, or evaluation results change.

Keep the README optimized for a peer reviewer who did not take the course.

The README must map project evidence to the scoring rubric.

Record significant decisions in `docs/decisions/` using a concise ADR format:

```text
Context
Decision
Consequences
Alternatives considered
```

Use `docs/plans/` for multi-step implementation plans. Plans should be updated as work progresses and should record unexpected findings and final outcomes.

## Git and change discipline

- Keep changes scoped to the requested task or current milestone.
- Do not reformat unrelated files.
- Do not rename public interfaces without updating all callers and documentation.
- Prefer small, coherent commits.
- Include tests and docs in the same change where appropriate.
- Do not commit secrets, local databases, model caches, indexed repository content, or generated evaluation outputs unless intentionally versioned.
- Preserve backwards compatibility unless the task explicitly authorizes a breaking change.

## Definition of task completion

A task is complete only when:

- the requested behavior works;
- relevant tests pass;
- linting and type checking pass;
- errors and edge cases are handled;
- observability is present where needed;
- documentation is updated;
- no unrelated scope was added;
- the implementation remains consistent with `PRD.md`;
- any deviation from the PRD is recorded as an explicit decision.

## First implementation objective

Unless instructed otherwise, begin with **M0 — Repository scaffold** and then **M1 — Searchable repository**.

The first vertical slice should:

1. load the current repository;
2. parse Python and Markdown files;
3. create typed chunks with paths, symbols, and line ranges;
4. index dense vectors in Qdrant;
5. expose a CLI search command;
6. return correct repository evidence;
7. include tests and setup documentation.

Do not implement the agent, Streamlit, Kestra, Grafana, or reranking before this slice works.
