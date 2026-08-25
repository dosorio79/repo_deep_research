# Evaluation

## Reviewer Evidence Paths

Evaluation evidence is available at two levels:

- Keyless review: `make stack-up` starts PostgreSQL and the API. The first
  evaluation API request initializes the schema and seeds curated retrieval and
  offline ground-truth answer summary rows, so `http://localhost:3000/evaluations`
  can be inspected without `OPENAI_API_KEY`.
- Reproducible reruns: retrieval evaluation can be rerun from the versioned
  datasets after ingesting the target repository. Answer generation and
  LLM-judge reruns are opt-in because they call OpenAI.

The committed source of truth for reviewers is this document plus the versioned
ground-truth records in `eval/development.json` and `eval/held_out.json`.
Generated raw reports under `eval/results/` are intentionally ignored.

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

To persist a refreshed retrieval run into the PostgreSQL-backed evaluation
dashboard, add `--persist` plus a readable source label:

```bash
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research \
uv run repo-research evaluate-retrieval \
  --path /home/daniel/code/dosorio79/datapeek \
  --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out-datapeek.json \
  --persist \
  --source-label "datapeek held-out retrieval" \
  --selected-mode dense
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
persisted. Full search-evaluation reports still come from the CLI and remain
reproducible through the versioned datasets and `make evaluate-retrieval`.

## Current Measured Retrieval Baseline

On 2026-08-14, the local alpha branch was evaluated at five results per
question against both the development self-repo dataset and the external
Datapeek held-out dataset. The generated reports remain ignored under
`eval/results/`; the curated measurements were:

| Dataset | Mode | File Hit Rate | File MRR | File Recall | File Precision | Symbol Hit Rate |
|---|---:|---:|---:|---:|---:|---:|
| Development | dense | 0.733 | 0.528 | 0.339 | 0.240 | 0.267 |
| Development | sparse | 0.133 | 0.036 | 0.089 | 0.030 | 0.000 |
| Development | hybrid | 0.600 | 0.383 | 0.228 | 0.157 | 0.267 |
| Datapeek held-out | dense | 0.800 | 0.602 | 0.542 | 0.319 | 0.600 |
| Datapeek held-out | sparse | 0.667 | 0.393 | 0.382 | 0.213 | 0.467 |
| Datapeek held-out | hybrid | 0.867 | 0.544 | 0.529 | 0.277 | 0.533 |

Dense retrieval remains the production default (`RDR_RETRIEVAL_MODE=dense`).
Hybrid finds at least one expected file slightly more often on Datapeek, but
dense has the stronger held-out rank, precision, recall, and symbol-hit
profile, so the default still favors the more precise evidence set.

## Relationship-Aware Graph Evaluation

The v0.6.1 relationship-aware development line includes a functional harness
for checking graph readiness and, optionally, answer-quality improvement. The
default command is offline and does not require an OpenAI key:

```bash
make evaluate-relationship-graph
```

It writes `artifacts/eval/relationship-aware/summary.json` plus separate
ingest and graph summaries. The graph checks fail if the current repository
artifact has no nodes, no edges, or no relationship counts.

When `OPENAI_API_KEY` is available, run the same harness with answer judging:

```bash
make evaluate-relationship-graph RUN_ANSWERS=1
```

That runs agentic `evaluate-answers` over `eval/development.json` with hybrid
retrieval and writes `answer-agentic-hybrid.json` and `answer-summary.json`.
To compare against a baseline report generated from `origin/dev`, call the
script directly:

```bash
uv run python scripts/evaluate_relationship_graph.py \
  --run-answers \
  --require-graph-expansion \
  --baseline-report artifacts/eval/baseline/answer-agentic-hybrid.json
```

Use the resulting `answer-comparison.json` to inspect candidate-minus-baseline
deltas for correctness, faithfulness, citation precision, reference coverage,
answer relevance, presentation quality, and unsupported claims. Retrieval-only
evaluation is still useful, but it does not measure graph expansion because the
graph is used after semantic retrieval inside bounded agentic research.
Use `--require-graph-expansion` for v0.6.1 acceptance runs so a live answer
evaluation fails when no judged row records graph expansion.
For a faster graph-specific live check, filter to relationship-heavy rows:

```bash
uv run python scripts/evaluate_relationship_graph.py \
  --path . \
  --run-answers \
  --require-graph-expansion \
  --question-type flow \
  --question-type change \
  --max-records 4 \
  --output-dir artifacts/eval/relationship-aware-v0.6.1-smoke
```

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
  --workers 6 \
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

For v0.6.1 and later, generated agentic dataset rows also preserve graph trace
fields: graph availability, expansion count, visited node count, relationship
counts, and fallback reason. These fields verify whether relationship-aware
change-impact answers actually used graph expansion; they do not change the
judge scoring rubric.

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
  --workers 6 \
  --output eval/results/answer-held-out-both.json
```

Generated answer reports remain under ignored `eval/results/`. Commit only
curated summary measurements, not transient local report files.

The completed 2026-08-16 Datapeek held-out run contains 30 judged rows: 15
direct and 15 agentic. Both approaches used dense retrieval. Scores are on the
0-5 judge scale unless otherwise noted.

| Approach | Count | Correctness | Faithfulness | Citation Precision | Reference Coverage | Relevance | Presentation | Unsupported Claims | Rows With Unsupported Claims | Avg Latency | Total Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct RAG | 15 | 2.667 | 4.300 | 4.667 | 2.267 | 4.167 | 4.133 | 20 | 73.3% | 16.6s | $0.0518 |
| Agentic research | 15 | 3.867 | 4.700 | 4.733 | 3.667 | 4.400 | 4.267 | 12 | 53.3% | 116.7s | $0.1400 |

Breakdown by held-out question type:

| Approach | Type | Count | Correctness | Faithfulness | Citation Precision | Reference Coverage | Unsupported Claims | Avg Latency | Total Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct RAG | locate | 5 | 2.800 | 4.200 | 4.600 | 2.800 | 4 | 10.0s | $0.0101 |
| Direct RAG | flow | 5 | 2.800 | 4.700 | 4.800 | 2.000 | 7 | 13.4s | $0.0165 |
| Direct RAG | change | 5 | 2.400 | 4.000 | 4.600 | 2.000 | 9 | 26.3s | $0.0252 |
| Agentic research | locate | 5 | 5.000 | 5.000 | 5.000 | 5.000 | 0 | 28.4s | $0.0377 |
| Agentic research | flow | 5 | 3.800 | 5.000 | 5.000 | 3.200 | 4 | 168.1s | $0.0451 |
| Agentic research | change | 5 | 2.800 | 4.100 | 4.200 | 2.800 | 8 | 153.7s | $0.0572 |

Interpretation: agentic research is the better quality path on this held-out
set, especially for locate questions where it found all expected evidence and
introduced no unsupported claims. The advantage is smaller and less consistent
on change-impact questions, where both approaches under-cover the manually
verified change set. Direct RAG remains much faster and cheaper, so it is still
useful for quick locate or exploratory questions; agentic research is the
preferred path when completeness and citation quality matter more than latency.

Dataset answer evaluation runs direct-RAG answer generation and answer judging
with bounded parallel workers. Shared-agent research generation remains
serialized to preserve tool/evidence validation state. Use `--workers` or
`RDR_ANSWER_EVALUATION_WORKERS` to tune throughput within the available OpenAI
rate limits.

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
summary rows. Fresh PostgreSQL volumes are seeded with the curated 2026-08-14
retrieval baseline for this repository and Datapeek, plus the curated 2026-08-16
Datapeek held-out direct-vs-agentic ground-truth answer summaries. Those seed
rows make the dashboard useful for reviewers who do not want to provide an
OpenAI key. Rerun retrieval evaluation after ingesting Datapeek when you need
new measurements for a changed commit. Detailed answer-evaluation run history
and per-question judge rows appear only after running `evaluate-answers
--persist`.

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
