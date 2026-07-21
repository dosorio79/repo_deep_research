# M0 — Repository scaffold

## Goal

Create a reproducible Python 3.12 foundation for Repo Deep Research without
implementing ingestion, retrieval, agentic research, UI, API, or monitoring
behaviour.

## Implementation plan

1. Establish the installable `src/repo_research` package and a validated,
   environment-driven settings model.
2. Define pinned application and development tooling in `pyproject.toml` and
   expose linting, formatting, type checking, and test commands through a
   Makefile.
3. Add a minimal Docker Compose service for Qdrant, including persistent local
   storage and a health check.
4. Add non-secret environment defaults, ignore rules, a CI workflow, and tests
   for the configuration boundary.
5. Document the current scope, setup, commands, configuration, and deliberately
   deferred M1+ capabilities in the README and setup guide.
6. Run formatting, linting, type checking, and tests; record the outcome below.

## Affected tests

- `tests/test_config.py`: default settings, environment overrides, and invalid
  settings validation.

## Acceptance checklist

- [x] Installable Python 3.12 package exists under `src/`.
- [x] Runtime configuration is centralized, typed, and validated from
  environment variables.
- [x] Docker Compose defines a health-checked Qdrant service with persistent
  data.
- [x] `make format`, `make lint`, `make typecheck`, and `make test` are
  available.
- [x] CI runs the quality checks on supported Python.
- [x] `.env.example` contains complete non-secret local defaults.
- [x] Initial documentation explains setup, scope, and commands.
- [x] No ingestion, retrieval, agent, UI, API, or monitoring implementation is
  introduced.
- [x] Validation results are recorded.

## Validation results

Completed on 2026-07-21:

- `make format` — passed
- `make lint` — passed
- `make typecheck` — passed (`mypy`: 3 source files)
- `make test` — passed (4 tests)
- `git diff --check` — passed
- `docker compose config --quiet` — passed
- `make docker-up` — passed; Qdrant reached `healthy` status
- `make docker-down` — passed; temporary smoke-test service was removed

Unexpected finding: Hatchling cannot infer a package from the hyphenated
project name and `src/` layout. The wheel target now explicitly includes
`src/repo_research`.

The Qdrant image does not include `wget`, so its initial HTTP health check was
unhealthy despite the service listening correctly. The Compose check now uses
the image's available Bash TCP probe.
