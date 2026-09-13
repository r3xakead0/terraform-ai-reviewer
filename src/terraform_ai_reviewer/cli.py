from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from terraform_ai_reviewer.checkov import build_deterministic_section, load_checkov
from terraform_ai_reviewer.config import load_config
from terraform_ai_reviewer.models import (
    AIAnalysis,
    AISection,
    ReviewMetadata,
    ReviewReport,
)
from terraform_ai_reviewer.plan import build_context, load_plan
from terraform_ai_reviewer.providers import load_fixture, review_with_bedrock
from terraform_ai_reviewer.render import render_markdown

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
DEFAULT_REGION = "us-east-1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="terraform-ai-review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("review", help="build an advisory review from plan artifacts")
    review.add_argument("--plan", type=Path, required=True)
    review.add_argument("--checkov", dest="checkov_path", type=Path, required=True)
    review.add_argument("--provider", choices=("bedrock", "fixture"), required=True)
    review.add_argument("--config", type=Path, default=Path("reviewer.yaml"))
    review.add_argument("--fixture", type=Path, default=Path("fixtures/bedrock-response.json"))
    review.add_argument("--model-id", default=os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID))
    review.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", DEFAULT_REGION)),
    )
    review.add_argument("--run-url", default=os.getenv("GITHUB_RUN_URL"))
    review.add_argument("--json-out", type=Path, required=True)
    review.add_argument("--markdown-out", type=Path, required=True)

    gate = subparsers.add_parser("gate", help="exit from the deterministic decision in a review")
    gate.add_argument("--review", type=Path, required=True)
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _limit_ai(section: AISection, limit: int) -> AISection:
    if section.status != "ok" or section.analysis is None:
        return section
    analysis = section.analysis
    return AISection(
        status="ok",
        analysis=AIAnalysis(
            overview=analysis.overview,
            risk_level=analysis.risk_level,
            findings=analysis.findings[:limit],
            questions=analysis.questions[:5],
        ),
    )


def _review(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    plan = load_plan(args.plan)
    deterministic = build_deterministic_section(load_checkov(args.checkov_path), config)
    context = build_context(plan, deterministic.findings, config.limits)

    if context.plan_summary.total_changed == 0:
        ai = AISection(status="skipped", message="No infrastructure changes; AI analysis skipped.")
    elif args.provider == "fixture":
        ai = load_fixture(args.fixture)
    else:
        ai = review_with_bedrock(context, args.model_id, args.region)
    ai = _limit_ai(ai, config.limits.max_ai_findings)

    input_truncated = any(
        (
            context.plan_summary.truncated_resources,
            context.plan_summary.truncated_attributes,
            context.plan_summary.truncated_values,
            deterministic.truncated_findings,
        )
    )
    report = ReviewReport(
        plan_summary=context.plan_summary,
        deterministic=deterministic,
        ai=ai,
        metadata=ReviewMetadata(
            provider=args.provider,
            model_id=args.model_id if args.provider == "bedrock" else None,
            input_truncated=input_truncated,
        ),
    )
    _write(args.json_out, report.model_dump_json(indent=2) + "\n")
    _write(
        args.markdown_out,
        render_markdown(report, args.run_url, config.limits.max_comment_chars),
    )
    print(
        f"Review created: deterministic gate={report.deterministic.decision}, "
        f"ai={report.ai.status}"
    )
    return 0


def _gate(args: argparse.Namespace) -> int:
    try:
        report = ReviewReport.model_validate_json(args.review.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise ValueError(f"invalid review report: {type(error).__name__}") from error
    if report.deterministic.decision == "block":
        print("Deterministic policy gate: BLOCK", file=sys.stderr)
        return 1
    print("Deterministic policy gate: PASS")
    return 0


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _review(args) if args.command == "review" else _gate(args)
    except Exception as error:
        print(f"terraform-ai-review: {error}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
