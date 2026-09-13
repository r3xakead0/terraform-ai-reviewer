provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.existing_oidc_provider_arn == null ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  tags           = var.tags
}

locals {
  oidc_provider_arn = var.existing_oidc_provider_arn != null ? (
    var.existing_oidc_provider_arn
  ) : aws_iam_openid_connect_provider.github[0].arn

  inference_profile_arn = join(":", [
    "arn",
    data.aws_partition.current.partition,
    "bedrock",
    var.aws_region,
    data.aws_caller_identity.current.account_id,
    "inference-profile/${var.inference_profile_id}",
  ])

  foundation_model_arns = [
    for region in var.destination_regions : join(":", [
      "arn",
      data.aws_partition.current.partition,
      "bedrock",
      region,
      "",
      "foundation-model/${var.foundation_model_id}",
    ])
  ]
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "GitHubPullRequestOIDC"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [var.github_oidc_subject]
    }
  }
}

resource "aws_iam_role" "reviewer" {
  name                 = var.role_name
  assume_role_policy   = data.aws_iam_policy_document.assume_role.json
  max_session_duration = 3600
  tags                 = var.tags
}

data "aws_iam_policy_document" "invoke_bedrock" {
  statement {
    sid       = "InvokeInferenceProfile"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.inference_profile_arn]
  }

  statement {
    sid       = "InvokeModelOnlyThroughProfile"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = local.foundation_model_arns

    condition {
      test     = "StringEquals"
      variable = "bedrock:InferenceProfileArn"
      values   = [local.inference_profile_arn]
    }
  }
}

resource "aws_iam_role_policy" "invoke_bedrock" {
  name   = "invoke-approved-bedrock-profile"
  role   = aws_iam_role.reviewer.id
  policy = data.aws_iam_policy_document.invoke_bedrock.json
}

