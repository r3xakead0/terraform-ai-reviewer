from __future__ import annotations

import json
from pathlib import Path

from terraform_ai_reviewer.cli import run

ROOT = Path(__file__).parents[1]


def _review_args(tmp_path: Path) -> list[str]:
    return [
        "review",
        "--plan",
        str(ROOT / "fixtures/tfplan.json"),
        "--checkov",
        str(ROOT / "fixtures/checkov.json"),
        "--provider",
        "fixture",
        "--fixture",
        str(ROOT / "fixtures/bedrock-response.json"),
        "--config",
        str(ROOT / "reviewer.yaml"),
        "--json-out",
        str(tmp_path / "review.json"),
        "--markdown-out",
        str(tmp_path / "review.md"),
    ]


def test_fixture_review_is_deterministic_and_blocks(tmp_path: Path) -> None:
    args = _review_args(tmp_path)
    assert run(args) == 0
    first_json = (tmp_path / "review.json").read_text()
    first_markdown = (tmp_path / "review.md").read_text()
    assert run(args) == 0
    assert (tmp_path / "review.json").read_text() == first_json
    assert (tmp_path / "review.md").read_text() == first_markdown

    report = json.loads(first_json)
    assert report["version"] == "1.0"
    assert report["deterministic"]["decision"] == "block"
    assert {
        finding["check_id"]
        for finding in report["deterministic"]["findings"]
        if finding["blocking"]
    } == {"CKV_AWS_24", "CKV_AWS_355", "CKV_AWS_21", "CKV2_AWS_6"}
    assert report["ai"]["status"] == "ok"
    assert run(["gate", "--review", str(tmp_path / "review.json")]) == 1


def test_invalid_plan_fails_closed_without_outputs(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-plan.json"
    invalid.write_text("not json")
    args = _review_args(tmp_path)
    args[2] = str(invalid)
    assert run(args) == 2
    assert not (tmp_path / "review.json").exists()


def test_invalid_checkov_fails_closed_without_outputs(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-checkov.json"
    invalid.write_text(json.dumps({"results": {"failed_checks": ["bad"]}}))
    args = _review_args(tmp_path)
    args[4] = str(invalid)
    assert run(args) == 2
    assert not (tmp_path / "review.json").exists()


def test_sensitive_values_never_reach_outputs_or_logs(tmp_path: Path, capsys) -> None:
    args = _review_args(tmp_path)
    assert run(args) == 0
    captured = capsys.readouterr()
    observable = "\n".join(
        [
            captured.out,
            captured.err,
            (tmp_path / "review.json").read_text(),
            (tmp_path / "review.md").read_text(),
        ]
    )
    assert "before-secret" not in observable
    assert "after-secret" not in observable


def test_no_changes_skips_ai(tmp_path: Path) -> None:
    plan = tmp_path / "empty-plan.json"
    checkov = tmp_path / "empty-checkov.json"
    plan.write_text(json.dumps({"format_version": "1.0", "resource_changes": []}))
    checkov.write_text(json.dumps({"results": {"failed_checks": []}}))
    args = _review_args(tmp_path)
    args[2] = str(plan)
    args[4] = str(checkov)
    assert run(args) == 0
    report = json.loads((tmp_path / "review.json").read_text())
    assert report["ai"]["status"] == "skipped"
    assert report["deterministic"]["decision"] == "pass"
    assert run(["gate", "--review", str(tmp_path / "review.json")]) == 0
