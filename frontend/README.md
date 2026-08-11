# Repo Deep Research Frontend

React TypeScript frontend for Repo Deep Research.

The frontend is a browser client for the FastAPI backend. It supports repository
ingestion, direct RAG, bounded agentic research, answer/evidence display,
feedback submission, and persisted monitoring views. It does not run retrieval
locally and does not generate answers in the browser.

## Backend Contract

The browser calls same-origin `/api` by default. Vite proxies `/api` to
`http://127.0.0.1:8000` for local development. Override `VITE_API_BASE_URL` when
a direct backend URL is needed, and `VITE_API_PROXY_TARGET` when the local API
runs somewhere else.

Important endpoints:

- `POST /repositories/ingest`
- `POST /rag`
- `POST /research`
- `POST /feedback`
- `GET /monitoring/summary`
- `GET /monitoring/runs`
- `GET /monitoring/runs/{request_id}`

Direct RAG requests use `limit`. Agentic research requests use
`retrieval_limit`.

## Development

You need Node.js matching `.nvmrc` and npm.

From the repository root, run the backend and frontend together:

```sh
make app
```

Or run the frontend directly:

```sh
cd frontend
npm install
npm test
npm run typecheck
npm run build
npm run dev
```

Run the API separately from the repository root when needed:

```sh
make api
```

The Vite dev server runs at `http://127.0.0.1:5173` and proxies `/api/*` to the
backend.
