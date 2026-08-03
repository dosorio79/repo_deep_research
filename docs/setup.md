# Setup

## Local development

Install Python 3.12 and uv, then create local environment files and sync the
pinned development dependencies:

```bash
cp .env.example .env
cp .env.local.example .env.local
make install
```

Use `.env` for stable non-secret defaults. Use `.env.local` for
`OPENAI_API_KEY` and other machine-local overrides. The application reads `.env`
first and `.env.local` second; exported shell variables still take precedence.

Run the required local validation suite:

```bash
make lint
make typecheck
make test
```

## Qdrant

The current local stack uses Qdrant as the only containerized dependency. Start
it with:

```bash
make docker-up
```

The service persists data in the Docker-managed `qdrant_storage` volume. Its
HTTP API and dashboard use port 6333 by default; change the host ports through
`QDRANT_HTTP_PORT` and `QDRANT_GRPC_PORT` in `.env` if needed. No collection is
created until the first repository ingestion.

Use `make docker-down` to stop the container. The named volume remains so local
data is preserved.

## Local embeddings

M1 uses FastEmbed with `BAAI/bge-small-en-v1.5`, which executes through ONNX
Runtime locally. The model downloads once into FastEmbed's local cache on first
ingestion; subsequent runs use that cache. No embedding API key or paid model
call is required. The default batch size is deliberately bounded to 16 for
predictable memory use during local repository indexing.

## OpenAI-backed direct RAG

M3 direct RAG uses the OpenAI Responses API only when running `rag`,
`api-rag`, `evaluate-answers`, or the `/rag` API endpoint. Set
`OPENAI_API_KEY` in `.env.local` or as an exported shell variable before live
answer generation:

```bash
export OPENAI_API_KEY=...
```

The default answer model is `RDR_OPENAI_ANSWER_MODEL=gpt-5-mini`; the default
judge model for opt-in answer evaluation is
`RDR_OPENAI_JUDGE_MODEL=gpt-5.1`.
Legacy `RDR_OPENAI_MODEL` remains accepted for existing local `.env` files.
Default unit tests use fake model adapters and do not require paid model calls.

Run the minimal API with:

```bash
make api
```

## Repository workflow

The project uses two long-lived branches:

- `main`: production.
- `dev`: integration and dev/preprod.

Feature branches should start from `dev`. Promote to production with a pull
request from `dev` to `main`, then tag `main` with the release version.

GitHub branch protection and environments are managed by Terraform:

```bash
export GITHUB_TOKEN="..."
terraform -chdir=infra/github init
terraform -chdir=infra/github plan \
  -var github_owner=dosorio79 \
  -var repository_name=repo_deep_research
```

Review the plan before applying it. The current M3 direct-RAG release is
`v0.3.0`.
