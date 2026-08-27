# Setup

## Local Development

Install Python 3.12 and uv, then create local environment files and sync the
Python dependencies:

```bash
cp .env.example .env
cp .env.local.example .env.local
make install
```

Use `.env` for stable non-secret defaults. Use `.env.local` for
`OPENAI_API_KEY` and other machine-local overrides. The application reads `.env`
first and `.env.local` second; exported shell variables still take precedence.

Run the backend validation suite:

```bash
make check
```

Run frontend checks directly with npm:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

## Local Services

Qdrant stores repository vectors. PostgreSQL stores monitoring, feedback, answer
snapshots, and evaluation results.

Start both services:

```bash
make services-up
```

Stop them:

```bash
make services-down
```

Qdrant persists data in the Docker-managed `qdrant_storage` volume. Its HTTP
API and dashboard use port 6333 by default; change the host ports through
`QDRANT_HTTP_PORT` and `QDRANT_GRPC_PORT` in `.env` if needed.

FastEmbed model files are cached at `RDR_FASTEMBED_CACHE_PATH` when it is set.
The example local environment uses `.cache/fastembed`, which is ignored by git.
If the app setting is unset, FastEmbed falls back to its own
`FASTEMBED_CACHE_PATH` environment variable or `/tmp/fastembed_cache`. Docker
Compose sets the API container cache path to `/root/.cache/fastembed` and mounts
the `fastembed_cache` volume there, so downloaded dense and sparse embedding
models are reused across container restarts. When a cache directory already has
files, the application tries FastEmbed in local-files-only mode first and falls
back to normal download behavior only if the cached files cannot load.

PostgreSQL persists data in the Docker-managed `postgres_storage` volume. The
local DSN in `.env.example` is:

```text
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research
```

Use `RDR_TELEMETRY_ENABLED=false` to run without persisted recording. When
telemetry is enabled but `RDR_POSTGRES_DSN` is unset, the app uses in-process
recording for ingestion job status and no-op recording for monitoring,
feedback, and evaluation data. Browser reload recovery for long ingestion runs
requires PostgreSQL persistence.

## OpenAI

Live RAG, agentic research, and answer evaluation require `OPENAI_API_KEY`.
Set it in `.env.local` or export it before running live commands:

```bash
export OPENAI_API_KEY=...
```

The default answer model is `RDR_OPENAI_ANSWER_MODEL=gpt-5-mini`; the default
judge model is `RDR_OPENAI_JUDGE_MODEL=gpt-5.1`. Unit tests use fake model
adapters and do not require paid model calls.

Reviewers can inspect evaluation evidence without a key. The Docker stack
initializes PostgreSQL tables and seeds curated retrieval and offline
ground-truth answer summary rows. Open `http://localhost:3000/evaluations`
after `make stack-up` to view those seeded metrics. Regenerating direct RAG,
agentic answers, or LLM-judge rows still requires `OPENAI_API_KEY`.

## Local Alpha BYOK Mode

`v0.5.9 Evaluation Evidence` is a local-only capstone review release. The expected user
path is:

```bash
cp .env.example .env
cp .env.local.example .env.local
# edit .env.local and set OPENAI_API_KEY
make install
make stack-up
```

Then open `http://localhost:3000`, ingest a local repository, run at least one
direct and one agentic question, submit feedback, and inspect the admin
evidence surfaces:

- `http://localhost:8000` redirects to Swagger UI
- `http://localhost:8000/docs`
- `http://localhost:3000/monitoring`
- `http://localhost:3000/evaluations`

For keyless capstone review, leave `OPENAI_API_KEY` blank and use the offline
evidence path instead:

```bash
cp .env.example .env
cp .env.local.example .env.local
make stack-up
```

Then inspect:

- `http://localhost:3000/evaluations` for seeded retrieval and offline
  ground-truth answer metrics.
- [docs/evaluation.md](evaluation.md) for metric definitions, dataset scope,
  and the current Datapeek held-out direct-vs-agentic comparison.
- [eval/development.json](../eval/development.json) and
  [eval/held_out.json](../eval/held_out.json) for the versioned ground-truth
  records.

This alpha does not target free hosted deployment. Running the full product
requires a browser frontend, FastAPI backend, Qdrant, PostgreSQL, local
repository access, and user-provided model credentials. The admin labels and
lock icons identify operator evidence views; they are not production
authentication in this local alpha.

Local Alpha validation checklist:

```bash
make install
make stack-up
make ingest
make rag QUESTION="where is configuration validated?"
make research QUESTION="which files handle answer evaluation persistence?"
make export-openapi
make test-all
```

After the RAG and research runs, confirm the browser can load the home page,
the admin `/monitoring` and `/evaluations` routes, and the API Swagger UI. The
API root `http://localhost:8000` redirects to `http://localhost:8000/docs`; the
generated OpenAPI contract is committed at `docs/api/openapi.json`.

## Full Stack

Start the production-like local stack:

```bash
make stack-up
```

The frontend is available at `http://localhost:3000`; the API is available at
`http://localhost:8000`. The frontend proxies API requests to the backend.

Use `make stack-rebuild` after Dockerfile, dependency, or frontend build
changes. Day-to-day alpha testing should use `make stack-up` so Docker can
reuse existing images. `make stack-stop` stops existing containers without
removing them; `make stack-start` starts those stopped containers again.

Stop the stack:

```bash
make stack-down
```

## Local App Mode

Run FastAPI with reload and the Vite dev server:

```bash
make app
```

This starts Qdrant, PostgreSQL, the API, and the frontend. The frontend is
available at `http://127.0.0.1:5173` and proxies `/api/*` to
`http://127.0.0.1:8000`.

## Optional Logfire

Logfire instrumentation is disabled by default. To enable local spans without
sending them to Logfire, set:

```text
RDR_LOGFIRE_ENABLED=true
RDR_LOGFIRE_SEND_TO_LOGFIRE=false
```

To send spans to Logfire, authenticate through Logfire's local setup and set
`RDR_LOGFIRE_SEND_TO_LOGFIRE=true`. The app instruments FastAPI and PydanticAI
without capturing headers, prompts, source content, or evidence excerpts as
custom payloads.

## Repository Workflow

The project uses two long-lived branches:

- `main`: production.
- `dev`: integration.

Feature branches start from `dev`. Promote to production with a pull request
from `dev` to `main`, then tag `main` with the release version. The current
release is `v0.6.5`.
