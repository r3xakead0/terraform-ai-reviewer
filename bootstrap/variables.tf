variable "aws_region" {
  description = "Source Region for the US geographic Bedrock inference profile."
  type        = string
  default     = "us-east-1"
}

variable "github_oidc_subject" {
  description = <<-EOT
    Exact GitHub OIDC subject for pull requests. Examples:
    repo:octo-org/octo-repo:pull_request
    repo:octo-org@123/octo-repo@456:pull_request
  EOT
  type        = string

  validation {
    condition     = can(regex("^repo:[^:]+:pull_request$", var.github_oidc_subject))
    error_message = "github_oidc_subject must be an exact repo subject ending in :pull_request."
  }
}

variable "existing_oidc_provider_arn" {
  description = "Existing token.actions.githubusercontent.com provider ARN; null creates it."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.existing_oidc_provider_arn == null ||
      can(regex("^arn:[^:]+:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.existing_oidc_provider_arn))
    )
    error_message = "existing_oidc_provider_arn must be the GitHub Actions OIDC provider ARN."
  }
}

variable "role_name" {
  description = "IAM role assumed by the pull-request review workflow."
  type        = string
  default     = "terraform-ai-reviewer"
}

variable "inference_profile_id" {
  description = "Bedrock geographic inference profile invoked by the reviewer."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
}

variable "foundation_model_id" {
  description = "Foundation model referenced by the geographic inference profile."
  type        = string
  default     = "anthropic.claude-sonnet-4-6"
}

variable "destination_regions" {
  description = "Regions used by the US profile when the request originates in us-east-1."
  type        = set(string)
  default     = ["us-east-1", "us-east-2", "us-west-2"]
}

variable "tags" {
  description = "Tags applied to IAM resources."
  type        = map(string)
  default = {
    Project   = "terraform-ai-reviewer"
    ManagedBy = "Terraform"
  }
}

