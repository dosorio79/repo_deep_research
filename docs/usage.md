# Usage

## Index a repository

Start Qdrant, then ingest either this repository or an explicit local path:

```bash
make docker-up
make ingest-self
# or: uv run repo-research ingest /path/to/python-repository
```

The command emits the repository name, root path, branch, commit hash, indexed
chunk count, `index_updated`, and any `skipped_files` diagnostics as JSON.
Re-running it upserts validated chunks before removing stale points, so an
embedding validation or Qdrant write failure retains the previously searchable
index. If every eligible file fails to parse, the command reports diagnostics
without replacing that index. Changed and removed paths do not persist as
current search results after a successful replacement.

The FastAPI app exposes the same ingestion boundary for the browser UI:

```bash
curl -s http://localhost:8000/repositories/ingest \
  -H 'content-type: application/json' \
  -d '{"repository_address":"/path/to/python-repository"}'
```

`repository_address` accepts a local path available to the backend. Public
`https://github.com/owner/repo(.git)` URLs are cloned once into
`RDR_REPOSITORY_CACHE_DIR` and then ingested through the same parser and Qdrant
replacement path.

## Search repository evidence

```bash
uv run repo-research search "where is repository configuration validated?"
```

Search emits JSON entries containing a score and a typed chunk. Each chunk
includes its path, symbol when applicable, line range, content, and structural
context. Select `--mode dense`, `--mode sparse`, or `--mode hybrid`; hybrid uses
Qdrant Reciprocal Rank Fusion. Evaluation selects the documented default mode,
but each CLI/API request may choose a retrieval mode independently.

Use `--path /path/to/repository` to search another already-indexed local
repository and `--limit 10` to change the number of returned results.

## Evaluate retrieval

After ingesting into the M2 `repo_chunks_v2` collection, compare baseline modes:

```bash
make evaluate-retrieval
uv run repo-research evaluate-retrieval --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out.json
```

The output reports file Hit Rate, MRR, Recall, Precision, and symbol Hit Rate
for each mode. The current held-out comparison selects dense as the production
default; see `docs/evaluation.md` for the recorded measurements.

## Answer with grounded direct RAG

After Qdrant is running, the repository is ingested, and `OPENAI_API_KEY` is set,
ask for a grounded answer:

```bash
make rag QUESTION="where is repository configuration validated?"
# or: uv run repo-research ask "where is repository configuration validated?" \
#       --mode locate --retrieval-mode dense --limit 5
```

Prefer keeping `OPENAI_API_KEY` in ignored `.env.local`; keep `.env` for
non-secret local defaults.

The command emits a `RagRunResult` JSON document with:

- `answer`: the grounded `RagAnswer` content, including summary, implementation
  flow, files and symbols, risks, unresolved questions, and canonical evidence
  items;
- `trace`: application-owned metadata for the run, including repository
  identity, retrieval settings, retrieved chunk count, unique file count, latency,
  model usage, estimated cost where pricing is known, and tool-call count.

Cost fields are telemetry only. They may be `null` when model pricing is
unknown, pricing is deliberately disabled, or provider usage metadata is
inconsistent; a pricing issue does not suppress a grounded answer.

The model cites opaque evidence IDs only; application code maps those IDs back to
stored paths and line ranges. Direct RAG preserves the result order returned by
the selected retrieval mode; it does not apply a second answer-time reranking
heuristic. Auto mode deterministically resolves common locate, flow, and
change-impact question wording, and locate/flow answers do not return change
targets. If retrieval or citation validation is insufficient, the command returns
an explicit `insufficient_evidence` answer instead of an unsupported claim; when
retrieval found nearby context, the answer still includes that closest evidence
for inspection.

Run the minimal backend for future UI integration:

```bash
make api
```

Then, in another terminal, exercise the same RAG service through FastAPI:

```bash
make api-rag QUESTION="where is repository configuration validated?"
```

## Answer with bounded agentic research

M4 adds a PydanticAI-backed research path for bounded, multi-step repository
investigation. Ensure Qdrant is running (e.g. `make docker-up`) and
`OPENAI_API_KEY` is set before running research. It keeps direct RAG on `/rag` and
reserves `/research` for the agentic `ResearchRunResult` contract:

```bash
uv run repo-research research "which modules must change to add bounded tools?" \
  --mode change --retrieval-mode dense --limit 5
```

The research command exposes optional budget flags:

```bash
--max-searches 3 --max-file-reads 5 --max-total-tool-calls 8
```

The service enforces those limits in application code for `search_repository`,
`read_chunk`, `read_file`, and `find_symbol`. File reads are scoped to the
requested repository root, and final evidence is canonicalized from tool results
so the agent cannot invent paths or line ranges. The response is a
`ResearchRunResult` with:

- `answer`: `ResearchAnswer`, including `research_steps`, implementation flow,
  evidence, change targets, risks, confidence, and unresolved questions;
- `trace`: the same application-owned trace metadata shape used by direct RAG,
  with `tool_call_count` populated for agentic tool use.

With the API running, callers may post the same request shape to:

```text
POST http://localhost:8000/research
```

Example JSON body:

```json
{
  "question": "which modules must change to add feedback persistence?",
  "mode": "change",
  "retrieval_mode": "dense",
  "retrieval_limit": 5,
  "budget": {
    "max_searches": 3,
    "max_file_reads": 5,
    "max_total_tool_calls": 8
  }
}
```

Direct RAG uses `limit`; agentic research uses `retrieval_limit`.

## Use the frontend harness

M3.6 includes a vendored React TypeScript frontend under `frontend/`. It is a
browser client for the FastAPI `/repositories/ingest`, `/rag`, and `/research`
contracts; it does not run retrieval locally or generate answers in the browser.

Install and check the frontend:

```bash
make frontend-install
make frontend-test
make frontend-typecheck
make frontend-build
```

Frontend Make targets use the Node version declared in `frontend/.nvmrc` when it
is installed under nvm.

Run the backend and frontend together:

```bash
make app
```

This starts Qdrant, the API, and the frontend only. Use the Research page to
enter and ingest the repository you want to inspect.

Or run them in separate terminals:

```bash
make api
make frontend-dev
```

The frontend defaults to `http://localhost:8000` and can post to `/rag` or
`/research`. Leave repository path blank to use the API server checkout, or
enter an absolute path available to the backend process. The API allows browser
origins only when `RDR_CORS_ALLOWED_ORIGINS` is configured as a JSON list.
`.env.example` opts in local frontend origins; keep that value restricted to
trusted development origins.

## Evaluate answers

Answer evaluation is live and opt-in because it calls OpenAI for both answer
generation and judging:

```bash
uv run repo-research evaluate-answers --dataset eval/development.json \
  --output eval/results/answer-development.json
```

Generated answer reports under `eval/results/` are ignored by git. Copy audited
summary numbers into documentation only after a deliberate held-out run.

## Supported source

The ingestion command indexes `.py`, `.md`, `.yaml`, `.yml`, `.toml`, and
`.json` files. It skips Git metadata, virtual environments, caches, build
outputs, `node_modules`, binary files, root `.gitignore` matches, and files
above `RDR_MAX_FILE_SIZE_BYTES`.
