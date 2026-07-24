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
