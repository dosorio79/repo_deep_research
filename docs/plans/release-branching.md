# Release and Branching Model

## Goal

Move the project to a small production-style workflow before M4 without adding a
third long-lived branch.

## Decision

- `main` is production.
- `dev` is the integration branch and dev/preprod environment.
- Feature branches start from `dev` and merge back to `dev`.
- Promotion to production happens by pull request from `dev` to `main`.
- Releases are GitHub Releases created from version tags on `main`.
- The current M3 direct-RAG state is the first release, `v0.3.0`.

## Terraform scope

The repository includes Terraform under `infra/github/` to manage GitHub
guardrails:

- create `dev` from `main` if needed;
- keep `main` as the default branch;
- protect `main` and `dev`;
- define `dev` and `prod` GitHub environments.

Terraform is intentionally limited to repository workflow settings. It does not
deploy application infrastructure.

## Release procedure

1. Work on a feature branch from `dev`.
2. Open a pull request into `dev`; CI must pass.
3. When ready for production, open a pull request from `dev` into `main`.
4. After merge, tag `main` with the next semantic version.
5. Push the tag; GitHub Actions creates the release.

For the first M3 release:

```bash
git checkout main
git pull origin main
git tag -a v0.3.0 -m "Release v0.3.0: M3 grounded direct RAG"
git push origin v0.3.0
```

## Validation

The branch model must keep the default quality gate small:

- `make lint`
- `make typecheck`
- `make test`

Docker, Qdrant, and live OpenAI checks remain local or opt-in until M4/M5 needs
a separate integration workflow.
