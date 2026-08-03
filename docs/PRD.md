# Product Requirements Document

## Product

**Repo Deep Research**

## Status

Initial implementation specification for the LLM Zoomcamp capstone.

## 1. Product summary

Repo Deep Research is an agentic RAG application for investigating Python repositories.

The application helps developers answer questions that are difficult to resolve through simple keyword search, such as:

- Where is a calculation or business rule implemented?
- How does data or control flow across modules?
- Which files and symbols must change to adapt a feature?
- Which configuration, tests, and downstream components may be affected?
- What evidence in the repository supports the answer?

The system ingests a repository, creates structured code and documentation chunks, indexes dense and sparse representations in Qdrant, and uses a PydanticAI agent to conduct bounded multi-step research. Answers must cite repository paths, symbols, and line ranges.

The project will demonstrate the main LLM Zoomcamp concepts in one coherent application: ingestion, hybrid retrieval, query rewriting, reranking, agentic tool use, retrieval evaluation, LLM evaluation, monitoring, feedback collection, containerization, and reproducibility.

## 2. Problem statement

Understanding an unfamiliar or evolving codebase often requires manually searching files, following imports, inspecting configuration, tracing function calls, and identifying tests. This is especially difficult when a calculation or feature spans several modules.

Traditional repository search can find exact strings but does not reliably explain:

- how retrieved code fragments connect;
- where the authoritative implementation lives;
- which modules participate in an execution flow;
- what must change to implement a requested adaptation;
- what risks or tests should be considered.

Repo Deep Research addresses this problem with retrieval grounded in the repository and a bounded research agent that can search, inspect, follow relevant evidence, and produce an actionable answer.

## 3. Target users

### Primary user

A developer, data scientist, or technical analyst who needs to understand a Python repository they did not write or have not worked on recently.

### Secondary user

A maintainer reviewing the likely impact of a proposed change before editing code.

## 4. Core use cases

### UC1 — Locate implementation

**Question**

> Where is token cost calculated?

**Expected result**

- Direct explanation
- Relevant files
- Relevant functions or classes
- Line ranges
- Evidence excerpts
- Confidence and uncertainties

### UC2 — Explain implementation flow

**Question**

> How does repository ingestion lead to hybrid retrieval?

**Expected result**

- Ordered flow across modules
- Key functions and data structures
- Configuration involved
- Evidence for each material claim

### UC3 — Change-impact analysis

**Question**

> Which modules must change to add a cross-encoder reranker?

**Expected result**

- Current implementation summary
- Files and symbols to modify
- Integration points
- Configuration changes
- Tests to add or update
- Risks and unresolved assumptions

### UC4 — Self-research demo

The application ingests and investigates its own repository.

This is the default capstone demonstration because reviewers can verify answers directly against the cited source files.

## 5. Product principles

1. **Evidence before explanation**  
   Material claims must be grounded in retrieved repository evidence.

2. **Useful uncertainty**  
   The system must state when evidence is incomplete or ambiguous.

3. **Bounded autonomy**  
   Research steps, searches, and file reads are limited to control latency and cost.

4. **Python-first scope**  
   Python repositories are supported deeply before additional languages are considered.

5. **Evaluation-driven retrieval**  
   The selected production retrieval approach must be justified by measured performance.

6. **Simple operations**  
   The complete application must run through Docker Compose with documented setup.

## 6. Scope

### In scope for the capstone

- Local repository ingestion
- Optional public GitHub repository cloning
- Python, Markdown, YAML, TOML, and JSON files
- Python AST-based structural parsing
- Repository-aware chunk metadata
- Qdrant dense retrieval
- Qdrant sparse lexical retrieval
- Hybrid retrieval with rank fusion
- Optional cross-encoder reranking
- Query rewriting
- One PydanticAI research agent
- Structured, cited answers
- Retrieval evaluation
- LLM answer evaluation
- FastAPI application interface
- React TypeScript user interface built with Lovable
- User feedback collection
- Logfire observability
- Monitoring dashboard with at least five useful charts
- Automated ingestion workflow
- Full Docker Compose setup
- Self-repository demonstration

### Explicit non-goals

- Automatic code modification
- Pull-request generation
- Compiler-grade static analysis
- Complete call-graph construction
- Arbitrary programming-language support
- Multi-repository research
- GitHub issue and pull-request ingestion
- Multi-agent orchestration
- Long-running autonomous agents
- Guaranteed change-impact completeness
- Production-grade authentication or multi-tenancy

## 7. Success criteria

### Product success

The system can ingest its own repository and accurately answer all three primary question types with verifiable citations.

### Retrieval success

A manually curated ground-truth set contains at least 30 questions across:

- locate implementation;
- explain flow;
- change-impact analysis.

Dense, sparse, and hybrid retrieval are evaluated. The best measured approach is used in the application.

Target metrics:

- Hit Rate@5 ≥ 0.80 at file level
- MRR ≥ 0.65 at file level
- Symbol Hit Rate@5 ≥ 0.65

These are targets, not acceptance blockers. Final results must be reported honestly.

### Answer success

At least two answer-generation approaches are compared.

Target average judge scores on a held-out set:

- groundedness ≥ 4/5;
- citation accuracy ≥ 4/5;
- correctness ≥ 3.5/5;
- change-plan usefulness ≥ 3.5/5.

### Operational success

- `docker compose up --build` starts all required services.
- Ingestion can be triggered without editing code.
- Dependency versions are pinned.
- Setup and usage are documented.
- User feedback is stored.
- Monitoring includes at least five charts or equivalent dashboard panels.

## 8. User experience

## 8.1 Main interface

The React TypeScript interface contains:

1. Repository selector
   - Current project repository
   - Local mounted path
   - Optional public GitHub URL

2. Question input

3. Research mode
   - Locate
   - Explain flow
   - Change impact
   - Auto-detect

4. Retrieval settings
   - Production default
   - Optional comparison mode for demonstration

5. Result sections
   - Answer
   - Implementation flow
   - Files and symbols
   - Change targets
   - Risks and uncertainties
   - Evidence
   - Research trace summary

6. Feedback
   - Useful
   - Not useful
   - Optional comment

## 8.2 API

Minimum endpoints:

```text
POST /repositories/ingest
GET  /repositories
POST /rag
POST /feedback
GET  /health
```

Optional evaluation endpoints are not required; evaluation may remain a CLI workflow.

## 9. Functional requirements

### FR1 — Repository discovery

The ingestion pipeline must:

- accept a local repository path;
- optionally clone a public GitHub repository;
- record repository name, branch, and commit hash;
- respect ignore rules;
- skip binary, generated, cache, environment, and large irrelevant files.

### FR2 — Structural parsing

For Python files, the parser must extract:

- module content;
- imports;
- classes;
- functions;
- methods;
- signatures;
- decorators;
- docstrings;
- start and end lines;
- parent symbol.

For Markdown, it must chunk by heading hierarchy.

For configuration files, it must preserve logical sections where practical.

### FR3 — Chunk model

Each chunk must include:

```text
chunk_id
repository_id
commit_hash
path
language
chunk_type
symbol
parent_symbol
start_line
end_line
content
context
content_hash
```

`context` may include file-level metadata, imports, heading hierarchy, or symbol signature.

### FR4 — Idempotent indexing

Repeated ingestion of the same commit must not create duplicate points.

Changed files must be re-indexed. Removed files must not remain active in the current repository version.

### FR5 — Retrieval modes

The retrieval layer must expose one common interface for:

- dense search;
- sparse search;
- hybrid search.

All modes must return a normalized `SearchResult` model.

### FR6 — Query rewriting

Before production retrieval, the system may transform a user question into one or more code-search-oriented queries.

The original question must remain available to the answer agent.

Rewriting must be evaluated against a no-rewrite baseline.

### FR7 — Reranking

A reranking stage may rerank the fused candidate set.

Reranking is a best-practice feature but must not block the first working version.

It must be evaluated against hybrid retrieval without reranking before becoming the production default.

### FR8 — Research agent

Use one PydanticAI agent with typed dependencies and structured output.

Minimum tools:

```text
search_repository
read_chunk
read_file
find_symbol
```

Optional:

```text
find_references
```

Bounds:

- maximum retrieval searches: 3;
- maximum file reads: 5;
- maximum total tool calls: 8.

These limits must be configurable.

### FR9 — Evidence-grounded output

The output must include:

- summary;
- implementation flow;
- evidence;
- relevant files and symbols;
- change targets when applicable;
- risks;
- confidence;
- unresolved questions.

Every evidence item must include:

- path;
- line range;
- symbol where available;
- reason for relevance.

The agent must not invent line ranges or source paths.

### FR10 — Insufficient-evidence behavior

When the repository does not support a conclusion, the answer must:

- state what could not be verified;
- identify the closest evidence found;
- avoid presenting speculation as fact;
- optionally suggest a narrower follow-up question.

### FR11 — Feedback

The UI must collect:

- positive or negative rating;
- optional free-text comment;
- request ID;
- repository and commit;
- retrieval configuration;
- timestamp.

### FR12 — Monitoring

The system must record:

- request count;
- end-to-end latency;
- retrieval latency;
- LLM latency;
- tool-call count;
- retrieved chunk count;
- unique files retrieved;
- input and output tokens;
- estimated cost where applicable;
- error count;
- positive feedback rate;
- question type;
- retrieval mode.

## 10. Technical architecture

```text
Repository path or public GitHub URL
                |
                v
      Automated ingestion workflow
                |
                v
       Repository loader and filters
                |
                v
      Python AST / document parsing
                |
                v
           Structured chunks
                |
        +-------+-------+
        |               |
        v               v
 Dense embeddings   Sparse embeddings
        |               |
        +-------+-------+
                |
                v
              Qdrant
                |
                v
 Dense / sparse / hybrid retrieval
                |
                v
      Optional candidate reranker
                |
                v
        PydanticAI research agent
                |
                v
 Structured answer with code evidence
                |
          +-----+------+
          |            |
          v            v
       FastAPI      Logfire
          |
          v
      React TypeScript UI
          |
          v
   Feedback and dashboard data
```

## 11. Proposed technology choices

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Package management | uv |
| Agent framework | PydanticAI |
| Validation | Pydantic |
| Vector and lexical database | Qdrant |
| Dense embeddings | FastEmbed-compatible dense model |
| Sparse embeddings | FastEmbed-compatible sparse model |
| Fusion | Reciprocal Rank Fusion |
| Reranking | Local cross-encoder, deferred until baseline works |
| API | FastAPI |
| UI | React TypeScript built with Lovable |
| Monitoring and traces | Logfire |
| Feedback store | SQLite initially |
| Evaluation | Python, pytest, pandas |
| Ingestion orchestration | Kestra or dlt; decide in ADR before implementation |
| Containers | Docker Compose |

## 12. Ingestion orchestration decision

The rubric awards full ingestion points for an automated pipeline using a dedicated tool.

Two acceptable options:

### Option A — Kestra

Advantages:

- directly demonstrates course material;
- clear visual workflow;
- good screenshot and demo value;
- explicit stages for clone, parse, embed, and index.

Disadvantages:

- heavier Docker Compose stack;
- additional workflow definitions and operational overhead.

### Option B — dlt

Advantages:

- Python-native;
- lower cognitive overhead;
- easier incremental and idempotent loading patterns.

Disadvantages:

- less visually demonstrable;
- may require custom handling around Qdrant writes.

### Decision rule

Use Kestra only if a minimal workflow can be added after the ingestion command works reliably.

The implementation must first expose an idempotent Python ingestion command. The orchestration layer calls that command rather than duplicating ingestion logic.

## 13. Monitoring dashboard

The rubric requires user feedback and a dashboard with at least five charts for full monitoring points.

Required panels:

1. Requests over time
2. End-to-end latency
3. Retrieval latency
4. Token usage or estimated cost
5. Positive feedback rate
6. Error rate
7. Average tool calls per research request

Logfire is the primary observability tool. A separate Grafana stack should only be added if Logfire cannot present the required dashboard clearly for reviewers.

## 14. Evaluation plan

## 14.1 Ground truth

Create at least 30 manually verified questions based on the project repository.

Distribution:

- 10 locate questions;
- 10 flow questions;
- 10 change-impact questions.

Each record includes:

```yaml
id: locate_001
question: Where is hybrid retrieval implemented?
question_type: locate
relevant_files:
  - src/repo_research/retrieval/hybrid.py
relevant_symbols:
  - HybridRetriever.search
notes: The answer should also mention collection configuration.
```

Split into:

- development set for iteration;
- held-out set for final reporting.

## 14.2 Retrieval experiments

Evaluate:

1. dense;
2. sparse;
3. hybrid;
4. hybrid plus query rewriting;
5. hybrid plus query rewriting and reranking, if implemented.

Metrics:

- Hit Rate@k;
- MRR;
- Recall@k;
- Precision@k;
- file-level Hit Rate;
- symbol-level Hit Rate.

The production configuration must be selected from measured results.

## 14.3 LLM experiments

Compare at least two approaches:

### Baseline

Single retrieval followed by a direct answer prompt.

### Agentic research

Bounded tool loop with structured output and evidence validation.

Optional third approach:

Agentic research with specialized change-impact instructions.

Judge dimensions:

- correctness;
- groundedness;
- citation accuracy;
- completeness;
- usefulness;
- unsupported-claim count.

## 15. Delivery milestones

### M0 — Repository scaffold

- package structure;
- configuration;
- Docker Compose with Qdrant;
- lint, type-check, and test commands;
- CI;
- initial documentation.

### M1 — Searchable repository

- repository loader;
- ignore rules;
- Python AST parser;
- Markdown and config parsing;
- chunk model;
- Qdrant dense indexing;
- CLI search command.

**Exit condition**

A query about the repository returns correct files, symbols, and line ranges.

### M1.1 — Ingestion reliability hardening

- validate embeddings before replacing current repository points;
- retain the last successful index when embedding or indexing fails;
- continue indexing eligible files when an individual file cannot be decoded or parsed;
- return structured skipped-file diagnostics from the ingestion command;
- cover ingestion and CLI success and failure paths with focused tests.

**Exit condition**

An unsuccessful ingestion does not remove previously searchable evidence, and
an eligible repository with individual unreadable or invalid source files still
returns indexed evidence plus actionable diagnostics.

### M2 — Evaluated hybrid retrieval

- sparse vectors;
- hybrid fusion;
- ground-truth dataset;
- evaluation CLI;
- dense versus sparse versus hybrid report.

**Exit condition**

A production retrieval mode is selected from measured results.

### M3 — Grounded RAG

- direct RAG baseline;
- citations;
- structured output;
- insufficient-evidence behavior;
- answer evaluation.

**Exit condition**

The system answers locate and flow questions with verifiable evidence.

### M3.5 — Observability contract

- response envelope around direct-RAG answers;
- application-owned run trace metadata;
- latency, retrieval, repository identity, model usage, and error fields;
- estimated price logging for known configured models;
- no frontend, persistence, Logfire, dashboard, or agentic behavior.

**Exit condition**

CLI and API direct-RAG responses expose stable answer-plus-trace JSON that can
later be logged or rendered without changing answer content.

### M3.6 — Lovable frontend testing harness

- React TypeScript frontend built with Lovable;
- question input;
- mode and retrieval selectors;
- answer and evidence rendering;
- trace/debug panel.

**Status**

On hold until M3.5 is complete. This is a manual testing harness, not the full
M5 product and operations milestone.

### M4 — Agentic deep research

- PydanticAI agent;
- typed dependencies;
- bounded tools;
- follow-up search;
- change-impact output;
- agentic trace metadata using the M3.5 response pattern.

**Exit condition**

The system produces a useful, evidence-backed change plan for its own repository.

### M5 — Product and operations

- FastAPI;
- product hardening for the React TypeScript frontend built with Lovable;
- feedback;
- Logfire;
- automated ingestion orchestration;
- complete Docker Compose;
- dashboard;
- README screenshots;
- preview video.

**Exit condition**

A reviewer can clone, configure, start, ingest, query, and inspect monitoring using only the documentation.

## 16. Priority model

### P0 — Required

- repository parsing;
- Qdrant dense, sparse, and hybrid retrieval;
- retrieval evaluation;
- direct RAG baseline;
- PydanticAI research agent;
- cited answers;
- FastAPI and React TypeScript frontend;
- feedback;
- monitoring;
- Docker Compose;
- reproducible README.

### P1 — Strong scoring features

- query rewriting;
- reranking;
- automated ingestion with Kestra or dlt;
- five-panel dashboard;
- self-repository demo;
- LLM evaluation comparison.

### P2 — Stretch

- public GitHub URL ingestion;
- symbol-reference heuristic;
- cloud deployment;
- incremental commit comparison;
- downloadable research report.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Scope grows into a general code intelligence platform | Keep Python-first and one repository per request |
| Retrieval returns adjacent but incorrect code | Evaluate file and symbol retrieval separately |
| Agent hallucinates relationships | Require citations and explicit uncertainty |
| Line ranges become stale | Associate indexed data with commit hash |
| Reranker consumes too much time | Defer until hybrid evaluation works |
| Kestra/Grafana dominate implementation time | Add only after core product passes exit conditions |
| Self-research appears circular | Include one second small public Python repository in evaluation or demo |
| Change impact cannot be guaranteed | Present it as evidence-backed guidance, not formal static analysis |

## 18. Documentation requirements

The README must include:

- problem and target user;
- architecture diagram;
- dataset/corpus description;
- supported files and limitations;
- ingestion process;
- retrieval approaches evaluated;
- final retrieval choice and metrics;
- LLM approaches evaluated;
- final prompting/agent choice;
- interface screenshots;
- monitoring dashboard screenshot;
- example questions and outputs;
- complete setup and run instructions;
- environment variables;
- Docker Compose usage;
- evaluation commands;
- mapping to every project scoring criterion;
- known limitations;
- short preview video.

Long material may move into:

```text
docs/setup.md
docs/architecture.md
docs/evaluation.md
docs/usage.md
docs/decisions/
```

## 19. Initial acceptance scenarios

### Scenario A — Locate

Given the repository is indexed, when the user asks where hybrid retrieval is implemented, the response identifies the correct file and symbol and cites valid line ranges.

### Scenario B — Flow

When the user asks how ingestion reaches Qdrant, the response lists the major processing stages in order and cites evidence from more than one module.

### Scenario C — Change impact

When the user asks how to add a reranker, the response identifies retrieval, configuration, evaluation, and test changes, clearly separating verified facts from recommendations.

### Scenario D — Missing evidence

When the user asks about authentication in a repository with no authentication implementation, the response states that no supporting implementation was found.

### Scenario E — Reproducibility

A reviewer can clone the repository at the submitted commit, create the environment file, run Docker Compose, ingest the repository, and submit a research question without modifying source code.

## 20. Definition of done

The capstone is complete when:

- all P0 requirements are implemented;
- multiple retrieval approaches are evaluated;
- multiple LLM approaches are evaluated;
- the best measured configurations are used;
- the application can research its own repository;
- answers contain verifiable evidence;
- feedback is collected;
- a dashboard exposes at least five useful metrics;
- all services run through Docker Compose;
- the project is reproducible from the README;
- documentation explicitly maps implementation evidence to the Zoomcamp rubric.
