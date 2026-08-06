# M4 live agentic research audit

Date: 2026-08-06
Branch: `feat/mvp-agentic-ui`
Commit: `51c67d97723897f8a096f3632aacde436ed27902`

## Purpose

Verify that the M4 bounded agentic research path works against this repository
with a real OpenAI-backed run and grounded repository evidence.

## Setup

Qdrant was started through the public Make target and the current repository was
ingested before the live run.

```bash
make ready
uv run repo-research research "which modules must change to add feedback persistence?" --mode change
```

The live command loaded `OPENAI_API_KEY` from the local environment. The key was
not printed or persisted.

## Result

The live run completed successfully.

| Field                 | Value                                      |
| --------------------- | ------------------------------------------ |
| request_id            | `1c7a8a3cc8d441878138b9695e4a1d2f`         |
| repository            | `repo_deep_research`                       |
| branch                | `feat/mvp-agentic-ui`                      |
| commit                | `51c67d97723897f8a096f3632aacde436ed27902` |
| question mode         | `change`                                   |
| retrieval mode        | `dense`                                    |
| retrieval limit       | `5`                                        |
| retrieved chunks      | `20`                                       |
| unique files          | `15`                                       |
| tool calls            | `7`                                        |
| total latency         | `86,772 ms`                                |
| model latency         | `86,736 ms`                                |
| insufficient evidence | `false`                                    |
| error                 | `null`                                     |

## Answer quality

The agent returned a usable change-impact answer for feedback persistence. It
identified model, API, runtime, research-service, frontend, and test/documentation
targets. It also separated implementation flow, risks, unresolved questions, and
evidence.

Representative cited evidence:

- `docs/PRD.md:380-440` for feedback and monitoring requirements.
- `src/repo_research/models.py:1-378` for typed models and `RagRunTrace`.
- `src/repo_research/api.py:1-162` for `/rag` and `/research` route wiring.
- `src/repo_research/runtime.py:1-73` for runtime factory wiring.
- `src/repo_research/research.py:355-358` for research-agent dependencies.
- `tests/test_models.py:114-171` for research trace contract coverage.

## Limitations

- `model_usage` was empty and `total_estimated_cost_usd` was `null`, so this
  run proves live behavior but does not yet prove cost accounting for M4.
- Retrieval latency was recorded as `0` for the agentic run while model latency
  carried nearly all elapsed time. That is acceptable for this first audit but
  should be revisited when monitoring metrics become part of the MVP.
- The answer recommended SQLite-style feedback persistence, which matches the
  capstone MVP plan, but the implementation is intentionally deferred to the
  feedback and monitoring slice.
