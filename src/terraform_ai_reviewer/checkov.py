from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from terraform_ai_reviewer.models import (
    DeterministicFinding,
    DeterministicSection,
    ReviewerConfig,
    Severity,
)


class CheckovError(ValueError):
    """Raised when Checkov output cannot be trusted."""


def load_checkov(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckovError(f"invalid Checkov JSON: {type(error).__name__}") from error


def _failed_checks(raw: Any) -> list[Mapping[str, Any]]:
    documents = raw if isinstance(raw, list) else [raw]
    failures: list[Mapping[str, Any]] = []
    recognized = False
    for document in documents:
        if not isinstance(document, Mapping):
            continue
        results = document.get("results")
        if not isinstance(results, Mapping):
            continue
        failed = results.get("failed_checks")
        if not isinstance(failed, list):
            raise CheckovError("Checkov results.failed_checks must be an array")
        recognized = True
        if not all(isinstance(item, Mapping) for item in failed):
            raise CheckovError("each Checkov failed check must be an object")
        failures.extend(failed)
    if not recognized:
        raise CheckovError("Checkov output does not contain a results object")
    return failures


def build_deterministic_section(raw: Any, config: ReviewerConfig) -> DeterministicSection:
    findings: list[DeterministicFinding] = []
    seen: set[tuple[str, str]] = set()

    for failure in _failed_checks(raw):
        check_id = failure.get("check_id")
        resource = failure.get("resource")
        if not isinstance(check_id, str) or not isinstance(resource, str):
            raise CheckovError("Checkov failed checks require check_id and resource")
        key = (check_id, resource)
        if key in seen:
            continue
        seen.add(key)

        policy = config.blocking_checks.get(check_id)
        name = failure.get("check_name")
        file_path = failure.get("file_path")
        guideline = failure.get("guideline")
        findings.append(
            DeterministicFinding(
                check_id=check_id,
                name=policy.name if policy else str(name or check_id),
                severity=policy.severity if policy else Severity.MEDIUM,
                category=policy.category if policy else "security",
                resource=resource,
                file_path=file_path if isinstance(file_path, str) else None,
                guideline=guideline if isinstance(guideline, str) else None,
                blocking=policy is not None,
            )
        )

    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }
    findings.sort(
        key=lambda item: (
            not item.blocking,
            severity_order[item.severity],
            item.check_id,
            item.resource,
        )
    )
    decision = "block" if any(item.blocking for item in findings) else "pass"
    limit = config.limits.max_deterministic_findings
    return DeterministicSection(
        decision=decision,
        findings=findings[:limit],
        truncated_findings=max(0, len(findings) - limit),
    )
