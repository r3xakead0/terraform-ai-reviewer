# AWS bootstrap

This root module creates the one-time trust relationship used by the reviewer. It is intentionally
separate from `demo/terraform`: the pull-request workflow never runs `terraform apply` and the
resulting role has no permission to modify infrastructure.

1. Enable access to Claude Sonnet 4.6 in Amazon Bedrock for the account.
2. Copy `terraform.tfvars.example` to an ignored `terraform.tfvars` and set the exact OIDC subject.
   Repositories created on or after July 15, 2026 normally include immutable owner and repository
   IDs in that subject.
3. If the account already has the GitHub OIDC provider, set `existing_oidc_provider_arn`.
4. Run `terraform init`, review `terraform plan`, and manually run `terraform apply`.
5. Add the `reviewer_role_arn` output to GitHub as the repository variable `AWS_ROLE_ARN`.

The default profile keeps inference within US Regions. Review the destination list and applicable
data-handling requirements before adapting this example to a real repository.
