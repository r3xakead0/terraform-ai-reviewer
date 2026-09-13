output "reviewer_role_arn" {
  description = "Set this value as the GitHub repository variable AWS_ROLE_ARN."
  value       = aws_iam_role.reviewer.arn
}

output "oidc_provider_arn" {
  description = "GitHub Actions OIDC provider used by the reviewer role."
  value       = local.oidc_provider_arn
}

output "bedrock_inference_profile_arn" {
  description = "Only Bedrock inference profile the reviewer role can invoke."
  value       = local.inference_profile_arn
}

