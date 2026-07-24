# Usage

## Index a repository

Start Qdrant, then ingest either this repository or an explicit local path:

```bash
make docker-up
make ingest-self
# or: uv run repo-research ingest /path/to/python-repository
```

The command emits the repository name, root path, branch, commit hash, indexed
chunk count, `index_updated`, and any `skipped_files` diagnostics as JSON.
Re-running it upserts validated chunks before removing stale points, so an
embedding validation or Qdrant write failure retains the previously searchable
index. If every eligible file fails to parse, the command reports diagnostics
without replacing that index. Changed and removed paths do not persist as
current search results after a successful replacement.

## Search repository evidence

```bash
uv run repo-research search "where is repository configuration validated?"
```

Search emits JSON entries containing a score and a typed chunk. Each chunk
includes its path, symbol when applicable, line range, content, and structural
context. Dense search is the only retrieval mode in M1.

Use `--path /path/to/repository` to search another already-indexed local
repository and `--limit 10` to change the number of returned results.

## Supported source

M1 indexes `.py`, `.md`, `.yaml`, `.yml`, `.toml`, and `.json` files. It skips
Git metadata, virtual environments, caches, build outputs, `node_modules`,
binary files, root `.gitignore` matches, and files above
`RDR_MAX_FILE_SIZE_BYTES`.
