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
research, and submit feedback. Monitoring at `/monitoring` and persisted answer
quality at `/evaluations` are admin/operator evidence views for local alpha
validation.

Use `make stack-rebuild` when Docker images need to be rebuilt after dependency,
Dockerfile, or frontend build changes.

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

After ingesting this repository into `repo_chunks_v2`, compare baseline modes
on the development dataset:

```bash
make ingest
make evaluate-retrieval
```

For the external Datapeek demo held-out dataset, ingest Datapeek first:

```bash
uv run repo-research ingest /home/daniel/code/dosorio79/datapeek
uv run repo-research evaluate-retrieval \
  --path /home/daniel/code/dosorio79/datapeek \
  --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out-datapeek.json
```

The output reports file Hit Rate, MRR, Recall, Precision, and symbol Hit Rate
for each mode. The Datapeek held-out set is a small public-demo repository, not
a broad benchmark. See `docs/evaluation.md` for dataset semantics and recorded
measurements.

## Evaluate Answers

Answer evaluation is live and opt-in because it calls OpenAI:

```bash
uv run repo-research evaluate-answers --dataset eval/development.json \
  --output eval/results/answer-development.json
```

Compare direct and agentic answers on a curated dataset:

```bash
uv run repo-research evaluate-answers --source dataset \
  --path /home/daniel/code/dosorio79/datapeek \
  --dataset eval/held_out.json --approach both \
  --output eval/results/answer-held-out-both.json
```

Judge recent monitored answers that were already returned by the UI or API and
persist the judge results to PostgreSQL:

```bash
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research \
uv run repo-research evaluate-answers --source monitored-runs \
  --run-kind agentic --limit 10 --persist \
  --output eval/results/answer-monitored-agentic.json
```

Use repeatable `--request-id` flags to judge specific recorded answers without
depending on recency or run-kind filters:

```bash
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research \
uv run repo-research evaluate-answers --source monitored-runs \
  --request-id 37d5381cf3494db78cbded95946c096a \
  --request-id 1198b2998eea4049b9f3eb0293821257 \
  --persist --output eval/results/answer-monitored-selected.json
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

Ingestion is request-driven and application-owned. The user selects a repository,
the backend accesses a local path or clones a public GitHub URL into
`RDR_REPOSITORY_CACHE_DIR`, supported files are parsed into typed chunks, local
FastEmbed dense and sparse embeddings are computed, and Qdrant is updated for
that repository commit. The Local Alpha does not use Kestra, dlt, Airflow, or
Prefect; scheduled ingestion is not the natural fit for arbitrary repositories
selected at request time.
