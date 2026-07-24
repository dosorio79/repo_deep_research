# Retrieval evaluation

## Purpose

M2 compares dense, sparse, and Qdrant RRF-hybrid retrieval using repository
evidence that is manually verified and versioned with the project.

## Datasets

- `eval/development.json` contains 15 records for iteration.
- `eval/held_out.json` contains 15 separate records for final reporting.

Together they contain ten locate, ten flow, and ten change-impact questions.
Each record names expected files, expected symbols where applicable, and a
human-verification note. Do not modify the held-out records to improve a
reported result.

## Run the comparison

After starting Qdrant and ingesting the repository into `repo_chunks_v2`, run:

```bash
make evaluate-retrieval
uv run repo-research evaluate-retrieval --dataset eval/held_out.json \
  --output eval/results/retrieval-held-out.json
```

The command writes a deterministic JSON report with one entry per retrieval
mode. Generated reports under `eval/results/` are ignored; copy final measured
results into review documentation only after the held-out run.

## Metrics

At the requested result limit (five by default), each mode reports:

- file Hit Rate;
- file MRR;
- file Recall;
- file Precision;
- symbol Hit Rate.

Use the held-out report to choose the production retrieval mode. The baseline
uses Qdrant Reciprocal Rank Fusion without tuned weights; query rewriting and
reranking are intentionally not part of this comparison.

## Measured baseline

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

Dense retrieval is therefore the production default (`RDR_RETRIEVAL_MODE=dense`)
for the next milestone. Hybrid remains available for future evaluated changes;
the measurements do not support making it the default yet.
