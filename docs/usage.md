# Usage

## Index a Repository

Start local services and ingest this repository:

```bash
make services-up
make ingest
```

To ingest another local repository, use the CLI directly:

```bash
uv run repo-research ingest /path/to/python-repository
```

The command emits repository identity, indexed chunk count, `index_updated`, and
any `skipped_files` diagnostics as JSON. Re-running ingestion upserts validated
chunks before removing stale points, so an embedding validation or Qdrant write
failure retains the previous searchable index.

The API exposes the same ingestion boundary:

```bash
curl -s http://127.0.0.1:8000/repositories/ingest \
  -H 'content-type: application/json' \
  -d '{"repository_address":"/path/to/python-repository"}'
```

`repository_address` accepts a local path available to the backend. Public
`https://github.com/owner/repo(.git)` URLs are cloned into
`RDR_REPOSITORY_CACHE_DIR` and ingested through the same parser and Qdrant
replacement path.

## Search Repository Evidence

```bash
uv run repo-research search "where is repository configuration validated?"
```

Search emits JSON entries containing a score and a typed chunk. Each chunk
includes path, symbol when applicable, line range, content, and structural
context. Select `--mode dense`, `--mode sparse`, or `--mode hybrid`; hybrid uses
Qdrant Reciprocal Rank Fusion.

Use `--path /path/to/repository` to search another already-indexed local
repository and `--limit 10` to change the number of returned results.

## Direct RAG

After services are running, the repository is ingested, and `OPENAI_API_KEY` is
set, ask for a grounded answer:

```bash
make rag QUESTION="where is repository configuration validated?"
```

Equivalent CLI form:

```bash
uv run repo-research ask "where is repository configuration validated?" \
  --mode locate --retrieval-mode dense --limit 5
```

The command emits a `RagRunResult` JSON document with:

- `answer`: grounded answer content, evidence, relevant files and symbols,
  risks, and unresolved questions.
- `trace`: application-owned metadata including repository identity, retrieval
  settings, chunk counts, latency, model usage, estimated cost, and tool-call
  count.

If retrieval or citation validation is insufficient, the command returns an
explicit `insufficient_evidence` answer instead of an unsupported claim.

## Bounded Agentic Research

Use the agentic path for multi-step repository investigation:

```bash
make research QUESTION="which modules must change to add bounded tools?"
```

Equivalent CLI form with explicit controls:

```bash
uv run repo-research research "which modules must change to add bounded tools?" \
  --mode change --retrieval-mode dense --limit 5 \
  --max-searches 5 --max-file-reads 6 --max-total-tool-calls 12
```

The service enforces budgets in application code for `search_repository`,
`read_chunk`, `read_file`, and `find_symbol`. File reads are scoped to the
requested repository root, and final evidence is canonicalized from tool
results so the agent cannot invent paths or line ranges.

With the API running, callers may post the same request shape to:

```text
POST http://127.0.0.1:8000/research
```

Direct RAG uses `limit`; agentic research uses `retrieval_limit`.

## Browser App

Run the containerized stack:

```bash
make stack-up
```

Open `http://localhost:3000`, ingest a repository, run direct or agentic
research, submit feedback, and inspect monitoring at `/monitoring`.

For local development:

```bash
make app
```

The Vite frontend runs at `http://127.0.0.1:5173` and proxies `/api/*` to
`http://127.0.0.1:8000`.

Frontend-only checks use npm directly:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

## Evaluate Retrieval

After ingesting into `repo_chunks_v2`, compare baseline modes:

```bash
make evaluate-retrieval
uv run repo-research evaluate-retrieval --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out.json
```

The output reports file Hit Rate, MRR, Recall, Precision, and symbol Hit Rate
for each mode. The current held-out comparison selects dense as the production
default; see `docs/evaluation.md` for recorded measurements.

## Evaluate Answers

Answer evaluation is live and opt-in because it calls OpenAI:

```bash
uv run repo-research evaluate-answers --dataset eval/development.json \
  --output eval/results/answer-development.json
```

Compare direct and agentic answers on a curated dataset:

```bash
uv run repo-research evaluate-answers --source dataset \
  --dataset eval/held_out.json --approach both \
  --output eval/results/answer-held-out-both.json
```

Judge recent monitored answers that were already returned by the UI or API and
persist the judge results to PostgreSQL:

```bash
uv run repo-research evaluate-answers --source monitored-runs \
  --run-kind agentic --limit 10 --persist \
  --output eval/results/answer-monitored-agentic.json
```

Persisted dataset evaluations are keyed by their versioned `record_id`.
Persisted monitored-run evaluations also keep the original answer `request_id`,
which links the judge result back to `answer_snapshots`.

After persisting results, open `/evaluations` in the frontend to inspect
aggregate scores, approach comparisons, run history, and the lowest-scoring
judged answers.

Generated reports under `eval/results/` are ignored by git. Commit only curated
summary measurements, not transient local report files.

## Supported Source

Ingestion indexes `.py`, `.md`, `.yaml`, `.yml`, `.toml`, and `.json` files. It
skips Git metadata, virtual environments, caches, build outputs, `node_modules`,
binary files, root `.gitignore` matches, and files above
`RDR_MAX_FILE_SIZE_BYTES`.
