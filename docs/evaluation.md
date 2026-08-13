# Evaluation

## Retrieval Evaluation

Retrieval evaluation compares dense, sparse, and Qdrant RRF-hybrid retrieval
using repository evidence that is manually verified and versioned with the
project.

Datasets:

- `eval/development.json` contains 15 records for iteration.
- `eval/held_out.json` contains 15 separate records for final reporting.

Together they contain ten locate, ten flow, and ten change-impact questions.
Each record names expected files, expected symbols where applicable, and a
human-verification note. Do not modify held-out records to improve a reported
result.

After starting services and ingesting the repository into `repo_chunks_v2`, run:

```bash
make evaluate-retrieval
uv run repo-research evaluate-retrieval --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out.json
```

Generated reports under `eval/results/` are ignored. Copy only curated summary
measurements into documentation.

Metrics at the requested result limit:

- file Hit Rate;
- file MRR;
- file Recall;
- file Precision;
- symbol Hit Rate.

Use the held-out report to choose the production retrieval mode. The baseline
uses Qdrant Reciprocal Rank Fusion without tuned weights; query rewriting and
reranking are intentionally not part of this comparison.

## Measured Retrieval Baseline

On 2026-07-24, commit `5e23291`, this repository was re-ingested into a local
`repo_chunks_v2` collection and evaluated at five results per question. The
generated reports are intentionally not committed; the audited measurements are:

| Dataset | Mode | File Hit Rate | File MRR | File Recall | File Precision | Symbol Hit Rate |
|---|---:|---:|---:|---:|---:|---:|
| Development | dense | 0.667 | 0.491 | 0.461 | 0.190 | 0.429 |
| Development | sparse | 0.267 | 0.139 | 0.222 | 0.066 | 0.071 |
| Development | hybrid | 0.467 | 0.347 | 0.294 | 0.112 | 0.286 |
| Held-out | dense | 0.733 | 0.539 | 0.589 | 0.247 | 0.600 |
| Held-out | sparse | 0.467 | 0.236 | 0.356 | 0.100 | 0.333 |
| Held-out | hybrid | 0.600 | 0.417 | 0.456 | 0.153 | 0.467 |

Dense retrieval is therefore the production default
(`RDR_RETRIEVAL_MODE=dense`). Hybrid remains available for future evaluated
changes; the measurements do not support making it the default yet.

## Answer Evaluation

Answer evaluation is opt-in because it calls OpenAI for judging. The default
command evaluates the direct-RAG dataset baseline:

```bash
uv run repo-research evaluate-answers --dataset eval/development.json \
  --output eval/results/answer-development.json
uv run repo-research evaluate-answers --dataset eval/held_out.json \
  --output eval/results/answer-held-out.json
```

Dataset evaluation can compare direct RAG against bounded agentic research:

```bash
uv run repo-research evaluate-answers --source dataset \
  --dataset eval/held_out.json --approach both \
  --output eval/results/answer-held-out-both.json
```

Persisted monitored answers can be judged without regenerating answers:

```bash
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research \
uv run repo-research evaluate-answers --source monitored-runs \
  --run-kind agentic --limit 10 --persist \
  --output eval/results/answer-monitored-agentic.json
```

Use `--request-id` when evaluating specific recorded answers:

```bash
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research \
uv run repo-research evaluate-answers --source monitored-runs \
  --request-id 37d5381cf3494db78cbded95946c096a \
  --request-id 1198b2998eea4049b9f3eb0293821257 \
  --persist --output eval/results/answer-monitored-selected.json
```

Answer evaluation uses two related rubrics:

- Ground Truth evaluation applies to versioned datasets with manually verified
  expected files, expected symbols, and human notes.
- Evidence Audit evaluation applies to persisted monitored answers. It judges
  the recorded answer against its returned evidence only; it is not a held-out
  correctness measurement.

The judge scores answer correctness, faithfulness, citation precision,
reference coverage, answer relevance, presentation quality, and unsupported
claim count. For monitored Evidence Audit runs, answer correctness and
reference coverage are unavailable because there is no independent ground-truth
record. The dashboard omits unavailable values from metric averages and shows
persisted answer evidence so evidence IDs can be inspected.

When `--persist` is supplied, dataset evaluations write `evaluation_results`
with the dataset `record_id` and no `request_id`, because generated dataset
answers are not stored in `answer_snapshots`. Monitored-run evaluations keep the
snapshot `request_id`, linking each result back to the original `/rag` or
`/research` answer returned by the UI or API.

Generated answer reports remain under ignored `eval/results/`. Commit only
curated summary measurements, not transient local report files.

## Evaluation Dashboard

PostgreSQL is the source of truth for the `/evaluations` dashboard. The
dashboard reads:

- `GET /evaluations/summary` for aggregate score cards and chart data.
- `GET /evaluations/runs` for recent persisted evaluation runs.
- `GET /evaluations/results` for individual judged answer rows.

Evaluation scores are scoped evidence, not global model scores. Dataset
evaluations are specific to the JSON dataset used for the run, and monitored-run
evaluations are specific to the repository that produced the original answer
snapshot. The dashboard exposes this as a repository-or-dataset context so users
can compare scores within the same source instead of mixing unrelated questions.

Run answer evaluation from the CLI with `--persist` to populate the dashboard.
Files under `eval/results/` remain optional exports for reproducible batch runs.
The dashboard is read-only and compares persisted dataset and monitored-run
evaluations without regenerating answers.
