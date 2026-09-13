from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from terraform_ai_reviewer.models import (
    AttributeChange,
    DeterministicFinding,
    Limits,
    PlanSummary,
    ResourceChange,
    ReviewContext,
)

REDACTED = "[REDACTED]"
UNKNOWN = "[KNOWN AFTER APPLY]"

_SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|private[_\-.]?key|access[_\-.]?key|"
    r"connection[_\-.]?string|client[_\-.]?secret",
    re.IGNORECASE,
)
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?<![A-Za-z0-9])[A-Za-z0-9_.-]*(?:password|passwd|secret|token|"
    r"private[_-]?key|access[_-]?key|connection[_-]?string|client[_-]?secret)"
    r"\s*[=:]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
)


class PlanError(ValueError):
    """Raised when Terraform plan JSON is invalid or unsupported."""


def load_plan(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"invalid Terraform plan JSON: {type(error).__name__}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("resource_changes", []), list):
        raise PlanError("Terraform plan must contain a resource_changes array")
    format_version = str(raw.get("format_version", "1.0"))
    if format_version.split(".", maxsplit=1)[0] != "1":
        raise PlanError(f"unsupported Terraform plan format major version: {format_version}")
    return raw


def classify_actions(actions: Sequence[str]) -> str | None:
    action_set = set(actions)
    if action_set in ({"no-op"}, {"read"}) or not action_set:
        return None
    if "create" in action_set and "delete" in action_set:
        return "replace"
    if action_set == {"create"}:
        return "create"
    if action_set == {"update"}:
        return "update"
    if action_set == {"delete"}:
        return "delete"
    raise PlanError(f"unsupported resource action sequence: {list(actions)}")


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY.search(key))


def _scrub_string(value: str) -> str:
    value = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    value = _AWS_ACCESS_KEY.sub("[REDACTED AWS ACCESS KEY]", value)
    value = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{REDACTED}", value)

    stripped = value.strip()
    if stripped.startswith(("{", "[")):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        return json.dumps(_sanitize(decoded, None), sort_keys=True, separators=(",", ":"))
    return value


def _child_mask(mask: Any, key: str | int) -> Any:
    if isinstance(mask, Mapping):
        return mask.get(str(key), mask.get(key))
    if isinstance(mask, list) and isinstance(key, int) and key < len(mask):
        return mask[key]
    return None


def _sanitize(value: Any, sensitive_mask: Any, key: str | None = None) -> Any:
    if sensitive_mask is True or (key is not None and _is_sensitive_key(key)):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(child_key): _sanitize(
                child_value,
                _child_mask(sensitive_mask, str(child_key)),
                str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize(child, _child_mask(sensitive_mask, index))
            for index, child in enumerate(value)
        ]
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def _overlay_unknown(value: Any, unknown_mask: Any) -> Any:
    if unknown_mask is True:
        return UNKNOWN
    if isinstance(value, Mapping):
        result = dict(value)
        if isinstance(unknown_mask, Mapping):
            for key, child_mask in unknown_mask.items():
                result[str(key)] = _overlay_unknown(result.get(str(key)), child_mask)
        return result
    if isinstance(value, list) and isinstance(unknown_mask, list):
        result = list(value)
        for index, child_mask in enumerate(unknown_mask):
            if index < len(result):
                result[index] = _overlay_unknown(result[index], child_mask)
        return result
    if isinstance(unknown_mask, Mapping):
        return {str(key): _overlay_unknown(None, child) for key, child in unknown_mask.items()}
    return value


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping) and value:
        flattened: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(child, path))
        return flattened
    if isinstance(value, list) and value:
        flattened = {}
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            flattened.update(_flatten(child, path))
        return flattened
    return {prefix or "$": value}


def _limit_value(value: Any, limit: int) -> tuple[Any, bool]:
    if isinstance(value, str) and value in {REDACTED, UNKNOWN}:
        return value, False
    if isinstance(value, str) and len(value) > limit:
        return f"{value[: limit - 1]}…", True
    return value, False


def _attribute_changes(
    change: Mapping[str, Any], limits: Limits
) -> tuple[list[AttributeChange], int, int]:
    before = _sanitize(change.get("before"), change.get("before_sensitive"))
    after = _sanitize(change.get("after"), change.get("after_sensitive"))
    after = _overlay_unknown(after, change.get("after_unknown"))

    before_flat = _flatten(before)
    after_flat = _flatten(after)
    changed: list[AttributeChange] = []
    truncated_values = 0
    for path in sorted(before_flat.keys() | after_flat.keys()):
        before_value = before_flat.get(path)
        after_value = after_flat.get(path)
        if before_value == after_value:
            continue
        before_value, before_truncated = _limit_value(before_value, limits.max_value_chars)
        after_value, after_truncated = _limit_value(after_value, limits.max_value_chars)
        truncated_values += int(before_truncated) + int(after_truncated)
        changed.append(
            AttributeChange(
                path=path,
                before=before_value,
                after=after_value,
            )
        )

    truncated = max(0, len(changed) - limits.max_attributes_per_resource)
    return changed[: limits.max_attributes_per_resource], truncated, truncated_values


def build_context(
    plan: Mapping[str, Any],
    findings: list[DeterministicFinding],
    limits: Limits,
) -> ReviewContext:
    resource_changes = plan.get("resource_changes", [])
    if not isinstance(resource_changes, list):
        raise PlanError("Terraform plan resource_changes must be an array")

    counts = {"create": 0, "update": 0, "delete": 0, "replace": 0}
    parsed: list[ResourceChange] = []
    truncated_attributes = 0
    truncated_values = 0

    for raw_resource in resource_changes:
        if not isinstance(raw_resource, Mapping):
            raise PlanError("each resource change must be an object")
        change = raw_resource.get("change")
        if not isinstance(change, Mapping):
            raise PlanError("each resource change must contain a change object")
        actions = change.get("actions", [])
        if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
            raise PlanError("resource change actions must be an array of strings")
        action = classify_actions(actions)
        if action is None:
            continue
        address = raw_resource.get("address")
        resource_type = raw_resource.get("type")
        if not isinstance(address, str) or not isinstance(resource_type, str):
            raise PlanError("changed resources require string address and type fields")

        counts[action] += 1
        attributes, attribute_truncations, value_truncations = _attribute_changes(change, limits)
        truncated_attributes += attribute_truncations
        truncated_values += value_truncations
        parsed.append(
            ResourceChange(
                address=address,
                resource_type=resource_type,
                action=action,
                attributes=attributes,
            )
        )

    priority = {"replace": 0, "delete": 1, "update": 2, "create": 3}
    parsed.sort(key=lambda item: (priority[item.action], item.address))
    truncated_resources = max(0, len(parsed) - limits.max_resources)
    summary = PlanSummary(
        **counts,
        total_changed=len(parsed),
        truncated_resources=truncated_resources,
        truncated_attributes=truncated_attributes,
        truncated_values=truncated_values,
    )
    return ReviewContext(
        plan_summary=summary,
        resources=parsed[: limits.max_resources],
        deterministic_findings=findings,
    )
