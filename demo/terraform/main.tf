locals {
  bucket_name = "terraform-ai-reviewer-${var.demo_suffix}"
}

resource "aws_security_group" "app" {
  name        = "terraform-ai-reviewer-app"
  description = "Plan-only application security group"
  vpc_id      = "vpc-00000000000000000"

  ingress {
    description = "Administrative SSH from the private operator network"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    description = "Application outbound access"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_policy" "app" {
  name = "terraform-ai-reviewer-app"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = ["arn:aws:s3:::${local.bucket_name}/*"]
    }]
  })
}

resource "aws_s3_bucket" "data" {
  bucket        = local.bucket_name
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
