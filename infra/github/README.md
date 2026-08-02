# GitHub Repository Management

This Terraform module manages the repository workflow guardrails.

## Branch model

- `main` is production.
- `dev` is the integration branch and also serves as dev/preprod.
- Feature work branches from `dev`.
- Releases are immutable `vMAJOR.MINOR.PATCH` tags cut from `main`.

There is no separate `preprod` branch.

## Managed resources

- Creates `dev` from `main` when it does not exist.
- Keeps `main` as the default branch.
- Protects `main` with required CI, pull-request review, linear history, and
  conversation resolution.
- Protects `dev` with required CI and no force-push or deletion.
- Creates GitHub environments named `dev` and `prod`.

## Usage

Authenticate the GitHub provider with a token that can administer the
repository:

```bash
export GITHUB_TOKEN="..."
terraform -chdir=infra/github init
terraform -chdir=infra/github plan \
  -var github_owner=dosorio79 \
  -var repository_name=repo_deep_research
```

Apply only after reviewing the plan:

```bash
terraform -chdir=infra/github apply \
  -var github_owner=dosorio79 \
  -var repository_name=repo_deep_research
```

The first release for the current M3 direct-RAG state is `v0.3.0`.
