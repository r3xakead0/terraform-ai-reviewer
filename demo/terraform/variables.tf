variable "aws_region" {
  description = "AWS Region used to construct the plan."
  type        = string
  default     = "us-east-1"
}

variable "demo_suffix" {
  description = "Suffix that makes the illustrative bucket name recognizable."
  type        = string
  default     = "change-me-1234567890"
}

