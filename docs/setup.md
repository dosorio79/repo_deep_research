# Setup

## Local development

Install Python 3.12 and uv, then create a local environment file and sync the
pinned development dependencies:

```bash
cp .env.example .env
make install
```

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

## OpenAI-backed research

M3 direct RAG uses the OpenAI Responses API only when running `research`,
`evaluate-answers`, or the `/research` API endpoint. Set `OPENAI_API_KEY` in the
environment or in `.env` before live answer generation:

```bash
export OPENAI_API_KEY="..."
```

The default answer model is `RDR_OPENAI_MODEL=gpt-5-mini`; the default judge
model for opt-in answer evaluation is `RDR_OPENAI_JUDGE_MODEL=gpt-5.1`.
Default unit tests use fake model adapters and do not require paid model calls.

Run the minimal API with:

```bash
make api
```
