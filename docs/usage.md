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

## Search repository evidence

```bash
uv run repo-research search "where is repository configuration validated?"
```

Search emits JSON entries containing a score and a typed chunk. Each chunk
includes its path, symbol when applicable, line range, content, and structural
context. Select `--mode dense`, `--mode sparse`, or `--mode hybrid`; hybrid uses
Qdrant Reciprocal Rank Fusion.

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
uv run repo-research research "where is repository configuration validated?" \
  --mode locate --retrieval-mode dense
```

The command emits a `ResearchAnswer` JSON document with a summary,
implementation flow, files and symbols, risks, unresolved questions, and
canonical evidence items. The model cites opaque evidence IDs only; application
code maps those IDs back to stored paths and line ranges. If retrieval or
citation validation is insufficient, the command returns an explicit
`insufficient_evidence` answer instead of an unsupported claim.

Run the minimal backend for future UI integration:

```bash
make api
curl -s http://127.0.0.1:8000/health
```

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
