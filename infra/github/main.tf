provider "github" {
  owner = var.github_owner
}

data "github_repository" "repo" {
  full_name = "${var.github_owner}/${var.repository_name}"
}

resource "github_branch" "dev" {
  repository    = var.repository_name
  branch        = "dev"
  source_branch = "main"
}

resource "github_branch_default" "main" {
  repository = var.repository_name
  branch     = "main"
}

resource "github_branch_protection" "main" {
  repository_id = data.github_repository.repo.node_id
  pattern       = "main"

  enforce_admins                  = false
  allows_deletions                = false
  allows_force_pushes             = false
  require_conversation_resolution = true
  required_linear_history         = true

  required_status_checks {
    strict   = true
    contexts = var.required_status_checks
  }

  required_pull_request_reviews {
    dismiss_stale_reviews           = true
    required_approving_review_count = 1
  }
}

resource "github_branch_protection" "dev" {
  repository_id = data.github_repository.repo.node_id
  pattern       = github_branch.dev.branch

  enforce_admins                  = false
  allows_deletions                = false
  allows_force_pushes             = false
  require_conversation_resolution = true

  required_status_checks {
    strict   = false
    contexts = var.required_status_checks
  }
}

resource "github_repository_environment" "dev" {
  repository  = var.repository_name
  environment = "dev"
}

resource "github_repository_environment" "prod" {
  repository  = var.repository_name
  environment = "prod"
}
