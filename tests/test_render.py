from __future__ import annotations

from terraform_ai_reviewer.models import (
    AIAnalysis,
    AIFinding,
    AISection,
    Confidence,
    DeterministicSection,
    PlanSummary,
    ReviewMetadata,
    ReviewReport,
    RiskLevel,
    Severity,
)
from terraform_ai_reviewer.render import DISCLAIMER, MARKER, render_markdown


def _report(overview: str = "Review overview") -> ReviewReport:
    return ReviewReport(
        plan_summary=PlanSummary(create=1, total_changed=1),
        deterministic=DeterministicSection(decision="pass"),
        ai=AISection(
            status="ok",
            analysis=AIAnalysis(
                overview=overview,
                risk_level=RiskLevel.MEDIUM,
                findings=[
                    AIFinding(
                        title="Review this change",
                        severity=Severity.MEDIUM,
                        category="operations",
                        resources=["terraform_data.example"],
                        evidence="An input changed.",
                        impact="Behavior may change.",
                        recommendation="Confirm the intended value.",
                        confidence=Confidence.HIGH,
                    )
                ],
                questions=["Is this expected?"],
            ),
        ),
        metadata=ReviewMetadata(provider="fixture"),
    )


def test_markdown_contains_sticky_marker_and_disclaimer() -> None:
    rendered = render_markdown(_report(), "https://github.com/example/run", 60_000)
    assert rendered.startswith(MARKER)
    assert "Deterministic gate: ✅ PASS" in rendered
    assert DISCLAIMER in rendered
    assert rendered.count("<details>") == rendered.count("</details>")


def test_markdown_truncation_preserves_closing_structure() -> None:
    rendered = render_markdown(_report("word " * 10_000), None, 1_600)
    assert len(rendered) <= 1_600
    assert "was truncated" in rendered
    assert rendered.endswith(f"> {DISCLAIMER}\n")
    assert rendered.count("<details>") == rendered.count("</details>")

