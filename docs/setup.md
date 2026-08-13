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

PostgreSQL persists data in the Docker-managed `postgres_storage` volume. The
local DSN in `.env.example` is:

```text
RDR_POSTGRES_DSN=postgresql://repo_research:repo_research@localhost:5432/repo_research
```

Use `RDR_TELEMETRY_ENABLED=false` to run without persisted recording. When
telemetry is enabled but `RDR_POSTGRES_DSN` is unset, the app uses an in-process
no-op recorder.

## OpenAI

Live RAG, agentic research, and answer evaluation require `OPENAI_API_KEY`.
Set it in `.env.local` or export it before running live commands:

```bash
export OPENAI_API_KEY=...
```

The default answer model is `RDR_OPENAI_ANSWER_MODEL=gpt-5-mini`; the default
judge model is `RDR_OPENAI_JUDGE_MODEL=gpt-5.1`. Unit tests use fake model
adapters and do not require paid model calls.

## Local Alpha BYOK Mode

`v0.5.8 Local Alpha` is planned as a local-only BYOK release. The expected user
path is:

```bash
cp .env.example .env
cp .env.local.example .env.local
# edit .env.local and set OPENAI_API_KEY
make install
make stack-up
```

Then open `http://localhost:3000`, ingest a local repository, run at least one
direct and one agentic question, submit feedback, and inspect:

- `http://localhost:3000/monitoring`
- `http://localhost:3000/evaluations`

This alpha does not target free hosted deployment. Running the full product
requires a browser frontend, FastAPI backend, Qdrant, PostgreSQL, local
repository access, and user-provided model credentials.

Local Alpha validation checklist:

```bash
make install
make stack-up
make ingest
make rag QUESTION="where is configuration validated?"
make research QUESTION="which files handle answer evaluation persistence?"
make test-all
```

After the RAG and research runs, confirm the browser can load the home page,
`/monitoring`, and `/evaluations`.

## Full Stack

Start the production-like local stack:

```bash
make stack-up
```

The frontend is available at `http://localhost:3000`; the API is available at
`http://localhost:8000`. The frontend proxies API requests to the backend.

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
from `dev` to `main`, then tag `main` with the release version.
