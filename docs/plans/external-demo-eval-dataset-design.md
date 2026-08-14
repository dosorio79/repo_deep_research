# External Demo Evaluation Dataset Design

## Goal

Recreate the versioned evaluation datasets so they match the current
`repo_deep_research` codebase and use `datapeek` as a small public-demo
external held-out repository.

## Scope

- Rebuild `eval/development.json` around the current `repo_deep_research`
  module layout.
- Rebuild `eval/held_out.json` around
  `/home/daniel/code/dosorio79/datapeek`.
- Keep the familiar 30-record shape unless implementation proves that
  `datapeek` cannot support 15 meaningful records: 15 development records and
  15 held-out records, balanced across `locate`, `flow`, and `change`.
- Treat `datapeek` as an external demo held-out set, not a broad benchmark.
- Keep generated evaluation reports under ignored `eval/results/`.

## Dataset Semantics

`eval/development.json` remains the iteration dataset for this project. Its
records should cite current modules such as `qdrant_store.py`, `rag.py`,
`research.py`, `recording_store.py`, `api.py`, `runtime.py`, `evaluation.py`,
`answer_evaluation.py`, and their focused tests.

`eval/held_out.json` becomes the external demo dataset. Its records should cite
real `datapeek` paths such as `app/main.py`, `app/routes/profile.py`,
`app/services/file_reader.py`, `app/services/s3_reader.py`,
`app/services/profiler.py`, `app/services/heuristics.py`,
`app/services/settings.py`, `app/services/profile_model.py`, `main.py`, and
`tests/`.

The documentation must explain that external held-out evaluation requires
ingesting `datapeek` before running `eval/held_out.json`. It must not imply that
the held-out results come from the `repo_deep_research` corpus.

## Validation

- Validate both JSON files through `load_records`.
- Keep record IDs disjoint.
- Keep question type counts balanced across 30 records:
  `{"change": 10, "flow": 10, "locate": 10}`.
- Add a deterministic test that prevents stale dataset paths from pointing to
  files absent from their intended repository.
- Run the narrow evaluation tests after dataset recreation.

## Documentation

Update `docs/evaluation.md` and `docs/usage.md` to show the two-repository
workflow:

1. ingest this repository for development evaluation;
2. ingest `/home/daniel/code/dosorio79/datapeek` for external demo held-out
   evaluation;
3. run `evaluate-retrieval` against the matching dataset.

Update README or release/runbook text only where it currently describes the
held-out dataset as self-repository-only.
