variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
}

variable "repository_name" {
  description = "Repository name without owner."
  type        = string
}

variable "required_status_checks" {
  description = "Status-check contexts required before protected branches can merge."
  type        = list(string)
  default     = ["quality"]
}
