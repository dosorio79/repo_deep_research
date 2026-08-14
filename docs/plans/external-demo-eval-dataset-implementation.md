# External Demo Evaluation Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recreate the versioned evaluation datasets so development questions target the current `repo_deep_research` codebase and held-out questions target `datapeek` as the external public-demo repository.

**Architecture:** Keep the existing JSON `EvaluationRecord` contract and deterministic evaluation loader. Add repository-aware dataset validation in tests and documentation rather than introducing a new dataset schema.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, existing `repo_research.evaluation.load_records`, JSON datasets under `eval/`, Markdown docs.

## Global Constraints

- Do not change production retrieval or answer-generation behavior.
- Do not add dependencies.
- Do not edit `/home/daniel/code/dosorio79/datapeek`; it is read-only source material for this task.
- Treat `eval/held_out.json` as an external demo held-out dataset, not a broad benchmark.
- Preserve 15 development records and 15 held-out records unless a testable reason proves that fewer held-out records are necessary.
- Preserve balanced question type counts across both datasets: 10 `locate`, 10 `flow`, 10 `change`.
- Do not commit generated `eval/results/` files.
- Do not commit changes unless the user explicitly asks.

---

## File Structure

- Modify `eval/development.json`: current `repo_deep_research` development records.
- Modify `eval/held_out.json`: external `datapeek` held-out records.
- Modify `tests/test_evaluation.py`: record-count/type checks plus path-existence checks against the correct repository roots.
- Modify `docs/evaluation.md`: explain the self-repo development and external demo held-out workflow.
- Modify `docs/usage.md`: update commands and caveats for ingesting the matching repository before running each dataset.
- Modify `README.md` only if it contains stale self-repo held-out wording.
- Do not modify `eval/mvp_change_questions.json` in this first pass unless tests reveal it conflicts with the new dataset contract.

---

### Task 1: Lock Dataset Validation Around Repository Roots

**Files:**
- Modify: `tests/test_evaluation.py`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `load_records(path: Path) -> list[EvaluationRecord]`
- Produces: pytest coverage that verifies dataset balance and real file paths for each dataset root.

- [ ] **Step 1: Update the existing dataset completeness test**

Replace `test_versioned_ground_truth_sets_are_complete_and_disjoint` with a repository-aware version:

```python
def test_versioned_ground_truth_sets_are_complete_disjoint_and_current() -> None:
    root = Path(__file__).parents[1]
    datapeek_root = root.parent / "datapeek"
    development = load_records(root / "eval/development.json")
    held_out = load_records(root / "eval/held_out.json")

    assert len(development) == 15
    assert len(held_out) == 15
    assert {record.id for record in development}.isdisjoint(
        record.id for record in held_out
    )
    audit = audit_evaluation_records({"development": development, "held_out": held_out})
    assert audit.record_count == 30
    assert audit.question_type_counts == {"change": 10, "flow": 10, "locate": 10}

    _assert_record_files_exist(development, root)
    _assert_record_files_exist(held_out, datapeek_root)
```

- [ ] **Step 2: Add a helper below the test**

```python
def _assert_record_files_exist(records: list[EvaluationRecord], repository_root: Path) -> None:
    missing = [
        f"{record.id}: {path}"
        for record in records
        for path in record.relevant_files
        if not (repository_root / path).exists()
    ]
    assert missing == []
```

- [ ] **Step 3: Run the focused test and verify it fails against the stale held-out dataset**

Run:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run pytest tests/test_evaluation.py::test_versioned_ground_truth_sets_are_complete_disjoint_and_current -q
```

Expected: FAIL with missing stale files such as `src/repo_research/db.py` when checked against the intended repository roots.

---

### Task 2: Recreate `eval/development.json` For Current `repo_deep_research`

**Files:**
- Modify: `eval/development.json`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `EvaluationRecord` fields `id`, `question`, `question_type`, `relevant_files`, `relevant_symbols`, `notes`.
- Produces: 15 self-repo development records with IDs `dev_locate_001` through `dev_change_005`.

- [ ] **Step 1: Replace `eval/development.json` with current records**

Use this content:

```json
[
  {
    "id": "dev_locate_001",
    "question": "Where is Qdrant collection setup and vector indexing implemented?",
    "question_type": "locate",
    "relevant_files": ["src/repo_research/qdrant_store.py"],
    "relevant_symbols": ["RepositoryDatabase"],
    "notes": "RepositoryDatabase owns collection setup, dense/sparse embedding use, and point replacement."
  },
  {
    "id": "dev_locate_002",
    "question": "Where is direct RAG answer generation implemented?",
    "question_type": "locate",
    "relevant_files": ["src/repo_research/rag.py"],
    "relevant_symbols": ["DirectRagService"],
    "notes": "DirectRagService assembles retrieved context, calls the answer generator, and validates citations."
  },
  {
    "id": "dev_locate_003",
    "question": "Where is bounded agentic research implemented?",
    "question_type": "locate",
    "relevant_files": ["src/repo_research/research.py"],
    "relevant_symbols": ["BoundedResearchService", "ResearchToolContext"],
    "notes": "BoundedResearchService and ResearchToolContext enforce tool budgets and produce grounded research answers."
  },
  {
    "id": "dev_locate_004",
    "question": "Where are persisted monitoring and evaluation rows stored?",
    "question_type": "locate",
    "relevant_files": ["src/repo_research/recording_store.py"],
    "relevant_symbols": ["PostgresRecordingStore"],
    "notes": "PostgresRecordingStore owns PostgreSQL persistence for runs, feedback, retrieval summaries, and evaluations."
  },
  {
    "id": "dev_locate_005",
    "question": "Where is runtime configuration loaded and validated?",
    "question_type": "locate",
    "relevant_files": ["src/repo_research/config.py"],
    "relevant_symbols": ["Settings"],
    "notes": "Settings centralizes environment-driven runtime configuration."
  },
  {
    "id": "dev_flow_001",
    "question": "How does the API create services for direct and agentic research requests?",
    "question_type": "flow",
    "relevant_files": ["src/repo_research/api.py", "src/repo_research/runtime.py", "src/repo_research/rag.py", "src/repo_research/research.py"],
    "relevant_symbols": ["create_app", "RuntimeServices", "DirectRagService", "BoundedResearchService"],
    "notes": "The FastAPI app uses runtime service factories to route requests to direct RAG or bounded research."
  },
  {
    "id": "dev_flow_002",
    "question": "How does repository ingestion parse files before indexing them?",
    "question_type": "flow",
    "relevant_files": ["src/repo_research/ingestion.py", "src/repo_research/models.py", "src/repo_research/qdrant_store.py"],
    "relevant_symbols": ["parse_files", "create_chunk", "RepositoryDatabase"],
    "notes": "Ingestion discovers eligible files, creates typed chunks, and hands them to the Qdrant store."
  },
  {
    "id": "dev_flow_003",
    "question": "How does retrieval evaluation run the same records across all retrieval modes?",
    "question_type": "flow",
    "relevant_files": ["src/repo_research/evaluation.py", "src/repo_research/models.py", "src/repo_research/qdrant_store.py"],
    "relevant_symbols": ["evaluate_records", "RetrievalMode", "RepositoryDatabase.search"],
    "notes": "evaluate_records iterates RetrievalMode and delegates each query to the configured RepositorySearcher."
  },
  {
    "id": "dev_flow_004",
    "question": "How does answer evaluation compare dataset answers and monitored runs?",
    "question_type": "flow",
    "relevant_files": ["src/repo_research/answer_evaluation.py", "src/repo_research/rag.py", "src/repo_research/research.py", "src/repo_research/recording_store.py"],
    "relevant_symbols": ["run_answer_evaluation", "load_dataset_records", "load_monitored_snapshots"],
    "notes": "Answer evaluation builds candidates from either versioned records or persisted snapshots and can persist judge results."
  },
  {
    "id": "dev_flow_005",
    "question": "How are unsupported or invalid citations checked before returning an answer?",
    "question_type": "flow",
    "relevant_files": ["src/repo_research/grounding.py", "src/repo_research/rag.py", "src/repo_research/research.py"],
    "relevant_symbols": ["validate_citations", "DirectRagService", "BoundedResearchService"],
    "notes": "Grounding validation checks answer evidence against retrieved or read chunks in direct and agentic paths."
  },
  {
    "id": "dev_change_001",
    "question": "Which files must change to add another retrieval mode?",
    "question_type": "change",
    "relevant_files": ["src/repo_research/models.py", "src/repo_research/qdrant_store.py", "src/repo_research/cli.py", "src/repo_research/evaluation.py", "tests/test_qdrant_store.py", "tests/test_cli.py"],
    "relevant_symbols": ["RetrievalMode", "RepositoryDatabase.search", "build_parser", "evaluate_records"],
    "notes": "A retrieval mode touches the enum, Qdrant search branch, CLI parser, evaluation loop, and tests."
  },
  {
    "id": "dev_change_002",
    "question": "Which files must change to add a new bounded research tool?",
    "question_type": "change",
    "relevant_files": ["src/repo_research/research.py", "src/repo_research/models.py", "tests/test_research.py"],
    "relevant_symbols": ["ResearchToolContext", "BoundedResearchService", "ResearchBudget"],
    "notes": "A new tool must respect budget accounting, structured output, and focused research tests."
  },
  {
    "id": "dev_change_003",
    "question": "Which files must change to expose a new API request option?",
    "question_type": "change",
    "relevant_files": ["src/repo_research/models.py", "src/repo_research/api.py", "src/repo_research/cli.py", "tests/test_api.py", "tests/test_cli.py"],
    "relevant_symbols": ["ResearchRequest", "create_app", "build_parser"],
    "notes": "Request options cross Pydantic models, FastAPI validation, CLI parsing, and contract tests."
  },
  {
    "id": "dev_change_004",
    "question": "Which files must change to add a new evaluation dashboard metric?",
    "question_type": "change",
    "relevant_files": ["src/repo_research/models.py", "src/repo_research/recording_store.py", "src/repo_research/api.py", "frontend/src/routes/evaluations.tsx", "tests/test_recording_store.py", "tests/test_api.py"],
    "relevant_symbols": ["EvaluationSummary", "PostgresRecordingStore", "create_app"],
    "notes": "Dashboard metrics require typed API shapes, SQL aggregation, route exposure, frontend rendering, and persistence/API tests."
  },
  {
    "id": "dev_change_005",
    "question": "Which files must change to update default model or retrieval settings?",
    "question_type": "change",
    "relevant_files": ["src/repo_research/config.py", ".env.example", "README.md", "docs/setup.md"],
    "relevant_symbols": ["Settings"],
    "notes": "Runtime defaults live in Settings and must stay aligned with environment examples and operator docs."
  }
]
```

- [ ] **Step 2: Validate JSON formatting**

Run:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run python -m json.tool eval/development.json >/tmp/repo_deep_research_development.json
```

Expected: command exits 0.

---

### Task 3: Recreate `eval/held_out.json` For `datapeek`

**Files:**
- Modify: `eval/held_out.json`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: current `datapeek` paths under `/home/daniel/code/dosorio79/datapeek`.
- Produces: 15 external demo held-out records with IDs `datapeek_locate_001` through `datapeek_change_005`.

- [ ] **Step 1: Replace `eval/held_out.json` with datapeek records**

Use this content:

```json
[
  {
    "id": "datapeek_locate_001",
    "question": "Where is the DatasetPeek Robyn application created and routes registered?",
    "question_type": "locate",
    "relevant_files": ["app/main.py"],
    "relevant_symbols": ["create_app"],
    "notes": "create_app builds the Robyn app, registers home/profile routes, and exposes static/health endpoints."
  },
  {
    "id": "datapeek_locate_002",
    "question": "Where does DatasetPeek handle the analyze upload route?",
    "question_type": "locate",
    "relevant_files": ["app/routes/profile.py"],
    "relevant_symbols": ["register_profile_routes"],
    "notes": "register_profile_routes owns GET/POST /analyze and calls file reading plus profile view-model assembly."
  },
  {
    "id": "datapeek_locate_003",
    "question": "Where are uploaded CSV and Parquet files validated and read?",
    "question_type": "locate",
    "relevant_files": ["app/services/file_reader.py"],
    "relevant_symbols": ["UploadedFile", "read_uploaded_file"],
    "notes": "UploadedFile normalizes local/S3 inputs and read_uploaded_file loads them into Polars."
  },
  {
    "id": "datapeek_locate_004",
    "question": "Where is the structured dataset profile built?",
    "question_type": "locate",
    "relevant_files": ["app/services/profiler.py"],
    "relevant_symbols": ["build_profile_model", "build_profile_view_model"],
    "notes": "The profiler builds structured profile data and template context from a Polars DataFrame."
  },
  {
    "id": "datapeek_locate_005",
    "question": "Where are DatasetPeek operational settings defined?",
    "question_type": "locate",
    "relevant_files": ["app/services/settings.py"],
    "relevant_symbols": ["AppSettings", "get_settings"],
    "notes": "Settings reads upload limits, preview sizes, text truncation, CSV inference, and S3 timeout options."
  },
  {
    "id": "datapeek_flow_001",
    "question": "How does a local upload become a rendered profile page?",
    "question_type": "flow",
    "relevant_files": ["app/routes/profile.py", "app/services/file_reader.py", "app/services/profiler.py", "app/services/profile_model.py"],
    "relevant_symbols": ["register_profile_routes", "UploadedFile.from_request_files", "read_uploaded_file", "build_profile_view_model"],
    "notes": "The route normalizes the upload, reads it with Polars, builds a profile view model, and renders home.html."
  },
  {
    "id": "datapeek_flow_002",
    "question": "How does DatasetPeek load an S3-compatible object for profiling?",
    "question_type": "flow",
    "relevant_files": ["app/routes/profile.py", "app/services/file_reader.py", "app/services/s3_reader.py", "app/services/settings.py"],
    "relevant_symbols": ["UploadedFile.from_s3_uri", "download_s3_object", "parse_s3_uri", "AppSettings"],
    "notes": "The analyze route detects an s3 URI, validates settings, downloads the object, and passes it through the same upload model."
  },
  {
    "id": "datapeek_flow_003",
    "question": "How are column roles and quality signals produced?",
    "question_type": "flow",
    "relevant_files": ["app/services/profiler.py", "app/services/heuristics.py", "app/services/profile_model.py"],
    "relevant_symbols": ["build_profile_model", "detect_column_role", "detect_column_signals", "ColumnSignal"],
    "notes": "The profiler collects column metrics, delegates role/signal heuristics, and stores results in structured profile models."
  },
  {
    "id": "datapeek_flow_004",
    "question": "How does DatasetPeek generate downloadable Markdown and HTML reports?",
    "question_type": "flow",
    "relevant_files": ["app/services/profiler.py", "app/services/profile_model.py"],
    "relevant_symbols": ["build_profile_model", "_markdown_report", "_html_report", "DatasetProfile"],
    "notes": "The profile model is enriched with generated report strings used by the rendered page."
  },
  {
    "id": "datapeek_flow_005",
    "question": "How does runtime host and port configuration reach the Robyn app?",
    "question_type": "flow",
    "relevant_files": ["main.py", "app/main.py"],
    "relevant_symbols": ["parse_runtime_config", "run"],
    "notes": "The root launcher parses HOST and PORT, then starts the module-level app through app.main.run."
  },
  {
    "id": "datapeek_change_001",
    "question": "Which files must change to add support for another upload file type?",
    "question_type": "change",
    "relevant_files": ["app/services/file_reader.py", "app/services/profiler.py", "README.md", "tests/test_app.py"],
    "relevant_symbols": ["UploadedFile", "read_uploaded_file", "build_profile_model"],
    "notes": "A new file type touches upload validation, Polars reading/profile assumptions, documentation, and service tests."
  },
  {
    "id": "datapeek_change_002",
    "question": "Which files must change to add another column quality heuristic?",
    "question_type": "change",
    "relevant_files": ["app/services/heuristics.py", "app/services/profiler.py", "app/services/profile_model.py", "tests/test_app.py"],
    "relevant_symbols": ["detect_column_signals", "build_profile_model", "ColumnSignal"],
    "notes": "Signals are detected in heuristics, assembled by the profiler, represented in profile models, and asserted in tests."
  },
  {
    "id": "datapeek_change_003",
    "question": "Which files must change to add a new operational setting?",
    "question_type": "change",
    "relevant_files": ["app/services/settings.py", "app/services/profiler.py", "README.md", "tests/test_settings.py", "tests/test_app.py"],
    "relevant_symbols": ["AppSettings", "get_settings", "build_profile_view_model"],
    "notes": "Operational settings are read from environment, used by profiling or reading code, documented, and covered by tests."
  },
  {
    "id": "datapeek_change_004",
    "question": "Which files must change to add a new route to the server-rendered app?",
    "question_type": "change",
    "relevant_files": ["app/main.py", "app/routes/home.py", "app/routes/profile.py", "tests/test_app.py"],
    "relevant_symbols": ["create_app", "register_home_routes", "register_profile_routes"],
    "notes": "New routes follow the route registration pattern and need app-level route tests."
  },
  {
    "id": "datapeek_change_005",
    "question": "Which files must change to improve S3-compatible object handling?",
    "question_type": "change",
    "relevant_files": ["app/services/s3_reader.py", "app/services/file_reader.py", "app/services/settings.py", "tests/test_s3_reader.py", "README.md"],
    "relevant_symbols": ["download_s3_object", "UploadedFile.from_s3_uri", "AppSettings"],
    "notes": "S3 behavior crosses URI parsing/download, file validation, credential/settings handling, tests, and user docs."
  }
]
```

- [ ] **Step 2: Validate JSON formatting**

Run:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run python -m json.tool eval/held_out.json >/tmp/repo_deep_research_held_out.json
```

Expected: command exits 0.

---

### Task 4: Update Evaluation Documentation For Two Repositories

**Files:**
- Modify: `docs/evaluation.md`
- Modify: `docs/usage.md`
- Modify: `README.md` if stale held-out wording is present

**Interfaces:**
- Consumes: existing CLI commands `make ingest-self`, `uv run repo-research ingest <path>`, `uv run repo-research evaluate-retrieval --dataset <path> --output <path>`.
- Produces: docs that tell users which repository must be ingested before each dataset run.

- [ ] **Step 1: Update `docs/evaluation.md` dataset description**

Replace the dataset bullet block with wording equivalent to:

```markdown
Datasets:

- `eval/development.json` contains 15 records for iteration against this
  repository.
- `eval/held_out.json` contains 15 records for external demo held-out reporting
  against `/home/daniel/code/dosorio79/datapeek`.

Together they contain ten locate, ten flow, and ten change-impact questions.
The held-out set is intentionally a small public-demo repository, not a broad
benchmark. Before running a dataset, ingest the repository that the dataset
targets.
```

- [ ] **Step 2: Update the retrieval command block in `docs/evaluation.md`**

Use commands equivalent to:

```bash
make ingest-self
make evaluate-retrieval

uv run repo-research ingest /home/daniel/code/dosorio79/datapeek
uv run repo-research evaluate-retrieval --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out-datapeek.json
```

- [ ] **Step 3: Update `docs/usage.md` evaluation section with the same two-repository workflow**

Ensure `docs/usage.md` states that `make evaluate-retrieval` is for the self-repo development dataset and the explicit `datapeek` ingest plus `eval/held_out.json` command is for external demo held-out reporting.

- [ ] **Step 4: Search for stale held-out claims**

Run:

```bash
rg -n "held-out|held_out|eval/held_out|self-repository|self repository|repo_deep_research corpus" README.md docs
```

Expected: output may include historical release notes. Update only current user-facing docs that describe the active evaluation workflow.

---

### Task 5: Run Focused Validation

**Files:**
- Test: `tests/test_evaluation.py`
- Test: JSON datasets
- Test: docs grep

**Interfaces:**
- Consumes: modified datasets, tests, and docs.
- Produces: verified focused pass or a concrete failure report.

- [ ] **Step 1: Run JSON validation**

Run:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run python -m json.tool eval/development.json >/tmp/repo_deep_research_development.json
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run python -m json.tool eval/held_out.json >/tmp/repo_deep_research_held_out.json
```

Expected: both commands exit 0.

- [ ] **Step 2: Run focused evaluation tests**

Run:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run pytest tests/test_evaluation.py -q
```

Expected: PASS.

- [ ] **Step 3: Run CLI parser tests if docs or defaults changed**

Run:

```bash
UV_CACHE_DIR=/tmp/repo_deep_research_uv_cache uv run pytest tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff -- eval/development.json eval/held_out.json tests/test_evaluation.py docs/evaluation.md docs/usage.md README.md
```

Expected: diff is limited to dataset recreation, repository-aware validation, and current evaluation documentation.

---

## Self-Review

- Spec coverage: Tasks cover dataset recreation, external demo semantics, validation, and docs.
- Placeholder scan: No task contains placeholder implementation instructions.
- Type consistency: Tests use existing `EvaluationRecord` and `load_records` contracts; no production schema changes are introduced.
