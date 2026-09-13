from __future__ import annotations

from pathlib import Path

import pytest

from terraform_ai_reviewer.checkov import CheckovError, build_deterministic_section
from terraform_ai_reviewer.config import load_config
from terraform_ai_reviewer.models import Severity

ROOT = Path(__file__).parents[1]


def test_blocking_and_advisory_findings_are_separate() -> None:
    raw = {
        "results": {
            "failed_checks": [
                {
                    "check_id": "CKV_AWS_18",
                    "check_name": "Logging",
                    "resource": "aws_s3_bucket.data",
                },
                {
                    "check_id": "CKV_AWS_24",
                    "check_name": "SSH",
                    "resource": "aws_security_group.app",
                },
            ]
        }
    }
    section = build_deterministic_section(raw, load_config(ROOT / "reviewer.yaml"))
    assert section.decision == "block"
    assert section.findings[0].check_id == "CKV_AWS_24"
    assert section.findings[0].blocking is True
    assert section.findings[0].severity == Severity.CRITICAL
    assert section.findings[1].blocking is False


def test_checkov_requires_results_object() -> None:
    with pytest.raises(CheckovError):
        build_deterministic_section({}, load_config(ROOT / "reviewer.yaml"))


def test_checkov_rejects_malformed_failed_check() -> None:
    with pytest.raises(CheckovError):
        build_deterministic_section(
            {"results": {"failed_checks": ["not-an-object"]}},
            load_config(ROOT / "reviewer.yaml"),
        )
