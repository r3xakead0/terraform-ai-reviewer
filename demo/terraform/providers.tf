provider "aws" {
  region = var.aws_region

  # This configuration is intentionally plan-only and never contacts AWS.
  # Do not copy these switches into a production root module.
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
}

