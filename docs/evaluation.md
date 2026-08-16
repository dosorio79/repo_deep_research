# Evaluation

## Retrieval Evaluation

Retrieval evaluation compares dense, sparse, and Qdrant RRF-hybrid retrieval
using repository evidence that is manually verified and versioned with the
project.

Datasets:

- `eval/development.json` contains 15 records for iteration against the Repo
  Deep Research repository.
- `eval/held_out.json` contains 15 records for external demo held-out reporting
  against the separate Datapeek repository at
  `/home/daniel/code/dosorio79/datapeek`.

Together they contain ten locate, ten flow, and ten change-impact questions.
Each record names expected files, expected symbols where applicable, and a
human-verification note. The held-out set is intentionally a small public-demo
repository, not a broad benchmark. Because the development set targets this
capstone repository and the held-out set targets Datapeek, held-out results are
cross-repository generalization evidence rather than only unseen questions from
the same repository. Before running a dataset, ingest the repository that the
dataset targets and pass that repository path to the evaluation command.

After starting services, run the development dataset against this repository:

```bash
make ingest
make evaluate-retrieval
```

Run the external demo held-out dataset after ingesting Datapeek:

```bash
uv run repo-research ingest /home/daniel/code/dosorio79/datapeek
uv run repo-research evaluate-retrieval \
  --path /home/daniel/code/dosorio79/datapeek \
  --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out-datapeek.json
```

Generated reports under `eval/results/` are ignored. Copy only curated summary
measurements into documentation.

Metrics at the requested result limit:

- file Hit Rate;
- file MRR;
- file Recall;
- file Precision;
- symbol Hit Rate.

Definitions:

| Metric | Definition | Interpretation |
|---|---|---|
| File Hit Rate | Share of questions where at least one expected file appears in the top `k` retrieved results. | Best quick signal that retrieval can find the right area of the repository. |
| File MRR | Mean reciprocal rank of the first expected file in the top `k` results. Questions with no hit contribute 0. | Rewards expected files appearing earlier in the ranked list. |
| File Recall | For each question, expected files found in top `k` divided by total expected files; then averaged. | Measures coverage of all expected files, not only the first hit. |
| File Precision | For each question, retrieved expected files divided by retrieved file results; then averaged. | Penalizes broad result sets that include many irrelevant files. |
| Symbol Hit Rate | Share of questions with expected symbols where at least one expected symbol appears in the top `k` results. | Applies only when the record declares relevant symbols. |

Use the held-out report to evaluate behavior on the external demo repository.
The baseline uses Qdrant Reciprocal Rank Fusion without tuned weights; query
rewriting and reranking are intentionally not part of this comparison.

The `/evaluations` dashboard can show read-only retrieval highlights so a local
alpha user can see retrieval quality before any answer-judge results have been
persisted. The seeded highlights are historical local-alpha measurements until
the external Datapeek held-out run is regenerated and persisted. Full
search-evaluation reports still come from the CLI and remain reproducible
through the versioned datasets and `make evaluate-retrieval`.

## Previous Measured Retrieval Baseline

On 2026-08-13, before the external Datapeek held-out refresh, the local alpha
branch was re-ingested into a local `repo_chunks_v2` collection and evaluated
at five results per question. The generated reports were intentionally not
committed; the audited historical measurements were:

| Dataset | Mode | File Hit Rate | File MRR | File Recall | File Precision | Symbol Hit Rate |
|---|---:|---:|---:|---:|---:|---:|
| Development | dense | 0.400 | 0.236 | 0.272 | 0.090 | 0.357 |
| Development | sparse | 0.067 | 0.033 | 0.067 | 0.013 | 0.071 |
| Development | hybrid | 0.333 | 0.163 | 0.250 | 0.077 | 0.357 |
| Held-out | dense | 0.467 | 0.313 | 0.311 | 0.200 | 0.400 |
| Held-out | sparse | 0.133 | 0.080 | 0.100 | 0.030 | 0.267 |
| Held-out | hybrid | 0.400 | 0.261 | 0.278 | 0.103 | 0.333 |

Dense retrieval remains the production default (`RDR_RETRIEVAL_MODE=dense`)
from the previous local-alpha measurement. Regenerate this section after
ingesting Datapeek and running the external demo held-out dataset.

## Answer Evaluation

Answer evaluation is opt-in because it calls OpenAI for judging. The default
command evaluates the direct-RAG dataset baseline:

```bash
uv run repo-research evaluate-answers --dataset eval/development.json \
  --output eval/results/answer-development.json
uv run repo-research evaluate-answers \
  --path /home/daniel/code/dosorio79/datapeek \
  --dataset eval/held_out.json \
  --output eval/results/answer-held-out.json
```

Dataset evaluation can compare direct RAG against bounded agentic research:

```bash
uv run repo-research evaluate-answers --source dataset \
  --path /home/daniel/code/dosorio79/datapeek \
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

The project already has two complementary answer-evaluation mechanisms:

- Offline Ground Truth evaluation is the controlled benchmark against versioned
  datasets with manually verified expected files, expected symbols, and human
  notes.
- Post-hoc monitored-run Evidence Audit evaluation judges real `/rag` and
  `/research` answers that were already persisted by the application. It checks
  the recorded answer against its returned evidence and supports operational
  quality review; it is not an independent held-out correctness measurement.

The judge scores answer correctness, faithfulness, citation precision,
reference coverage, answer relevance, presentation quality, and unsupported
claim count. For monitored Evidence Audit runs, answer correctness and
reference coverage are unavailable because there is no independent ground-truth
record. The dashboard omits unavailable values from metric averages and shows
persisted answer evidence so evidence IDs can be inspected.

Answer-evaluation metric definitions:

| Metric | Scale | Available for | Definition |
|---|---:|---|---|
| Answer correctness | 0-5, nullable | Ground Truth dataset runs | How well the answer matches the manually verified expected files, symbols, and notes. |
| Faithfulness | 0-5 | Ground Truth and Evidence Audit | Whether claims in the answer are supported by cited repository evidence. |
| Citation precision | 0-5 | Ground Truth and Evidence Audit | Whether cited evidence IDs actually support the claims attached to them. |
| Reference coverage | 0-5, nullable | Ground Truth dataset runs | How completely the answer cites the expected files or symbols from the dataset record. |
| Answer relevance | 0-5 | Ground Truth and Evidence Audit | Whether the answer addresses the user question without drifting into unrelated implementation detail. |
| Presentation quality | 0-5 | Ground Truth and Evidence Audit | Whether the answer is structured, concise, and useful for a technical reader. |
| Unsupported claim count | Count | Ground Truth and Evidence Audit | Number of material answer claims the judge identifies as unsupported by evidence. |

Dashboard average score is intentionally conservative and comparable across
Ground Truth and Evidence Audit rows. It averages only the metrics that exist in
both modes: faithfulness, citation precision, answer relevance, and
presentation quality. Ground-truth-only fields remain visible in the table but
are not part of the cross-mode average.

## Held-out Direct-vs-Agentic Comparison

The final held-out answer comparison uses the existing Ground Truth evaluator
against Datapeek:

```bash
uv run repo-research ingest /home/daniel/code/dosorio79/datapeek
uv run repo-research evaluate-answers \
  --path /home/daniel/code/dosorio79/datapeek \
  --source dataset \
  --dataset eval/held_out.json \
  --approach both \
  --retrieval-mode dense \
  --output eval/results/answer-held-out-both.json
```

Generated answer reports remain under ignored `eval/results/`. Commit only
curated summary measurements, not transient local report files. When the report
is available, summarize direct and agentic averages for answer correctness,
faithfulness, citation precision, reference coverage, answer relevance,
presentation quality, unsupported claim count, and available operational fields
such as latency, estimated cost, and any linked token-usage or tool-call
telemetry. Add locate/flow/change-impact breakdowns by joining results to
`eval/held_out.json` through `record_id` if the existing result records support
it cleanly; do not change the evaluation framework only to create that
breakdown.

Interpretation should follow the evidence. A valid conclusion may prefer direct
RAG overall, prefer agentic research overall, recommend different approaches by
question type, or find no meaningful quality preference. Latency, token usage,
estimated cost, and tool calls are secondary operational considerations when
quality is comparable; they should not be mixed into the ground-truth quality
score or used to change routing defaults solely for rubric purposes.

When `--persist` is supplied, dataset evaluations write `evaluation_results`
with the dataset `record_id` and no `request_id`, because generated dataset
answers are not stored in `answer_snapshots`. Monitored-run evaluations keep the
snapshot `request_id`, linking each result back to the original `/rag` or
`/research` answer returned by the UI or API.

## Evaluation Dashboard

PostgreSQL is the source of truth for the `/evaluations` dashboard. The
dashboard reads:

- `GET /evaluations/summary` for aggregate score cards and chart data.
- `GET /evaluations/runs` for recent persisted evaluation runs.
- `GET /evaluations/results` for individual judged answer rows.

Search-evaluation highlights on this page come from PostgreSQL retrieval
summary rows. The default seeded rows are historical local-alpha measurements;
rerun retrieval evaluation after ingesting Datapeek before presenting them as
the current `eval/held_out.json` external demo baseline. Answer-evaluation
charts and tables reflect persisted PostgreSQL rows.

Evaluation scores are scoped evidence, not global model scores. Dataset
evaluations are specific to the JSON dataset used for the run, and monitored-run
evaluations are specific to the repository that produced the original answer
snapshot. The dashboard exposes this as a repository-or-dataset context so users
can compare scores within the same source instead of mixing unrelated questions.
Where comparable or same-question direct and agentic runs have been persisted,
the dashboard lets an operator inspect those approaches side by side without
regenerating answers.

Run answer evaluation from the CLI with `--persist` to populate the dashboard.
Files under `eval/results/` remain optional exports for reproducible batch runs.
The dashboard is read-only and compares persisted dataset and monitored-run
evaluations without regenerating answers.
