from __future__ import annotations

import html
from urllib.parse import urlparse

from terraform_ai_reviewer.models import ReviewReport

MARKER = "<!-- terraform-ai-reviewer -->"
DISCLAIMER = (
    "AI analysis is advisory and may be incomplete. The merge decision above is based only on "
    "deterministic policy checks; a human must approve any apply."
)


def _text(value: object, limit: int = 700) -> str:
    cleaned = " ".join(str(value).split())
    cleaned = html.escape(cleaned, quote=False).replace("|", "\\|")
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1]}…"


def _safe_link(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} else ""


def render_markdown(report: ReviewReport, run_url: str | None, max_chars: int) -> str:
    summary = report.plan_summary
    blocked = report.deterministic.decision == "block"
    status = "🚫 BLOCK" if blocked else "✅ PASS"
    run_link = f" · [Workflow run]({_safe_link(run_url)})" if _safe_link(run_url) else ""

    header = [
        MARKER,
        "## 🤖 Terraform AI Review",
        "",
        f"**Deterministic gate: {status}**{run_link}",
        "",
        "| Create | Update | Delete | Replace | Total |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {summary.create} | {summary.update} | {summary.delete} | "
            f"{summary.replace} | {summary.total_changed} |"
        ),
        "",
    ]
    if any(
        (summary.truncated_resources, summary.truncated_attributes, summary.truncated_values)
    ):
        header.extend(
            [
                (
                    "_Sanitized model input was truncated: "
                    f"{summary.truncated_resources} resources, "
                    f"{summary.truncated_attributes} attributes, and "
                    f"{summary.truncated_values} values._"
                ),
                "",
            ]
        )
    header.extend(["### Deterministic policy findings", ""])

    deterministic_lines: list[str] = []
    if not report.deterministic.findings:
        deterministic_lines.append("No policy violations found.")
    for finding in report.deterministic.findings:
        label = "BLOCKING" if finding.blocking else "ADVISORY"
        guideline = _safe_link(finding.guideline)
        check = f"[{finding.check_id}]({guideline})" if guideline else finding.check_id
        location = f" · `{_text(finding.file_path, 200)}`" if finding.file_path else ""
        deterministic_lines.extend(
            [
                (
                    f"- **{_text(finding.severity.value.upper())} · {label} · {check}** — "
                    f"{_text(finding.name)}"
                ),
                f"  Resource: `{_text(finding.resource, 300)}`{location}",
            ]
        )
    if report.deterministic.truncated_findings:
        deterministic_lines.append(
            f"- {report.deterministic.truncated_findings} additional findings were omitted."
        )

    ai_lines = [
        "",
        "<details>",
        "<summary><strong>AI-generated advisory analysis</strong></summary>",
        "",
    ]
    if report.ai.status == "skipped":
        skipped = report.ai.message or "No infrastructure changes; AI analysis skipped."
        ai_lines.append(_text(skipped))
    elif report.ai.status == "unavailable":
        ai_lines.append(f"⚠️ {_text(report.ai.message or 'AI analysis unavailable.')}")
    elif report.ai.analysis:
        analysis = report.ai.analysis
        ai_lines.extend(
            [
                f"**Advisory risk level:** {_text(analysis.risk_level.value.upper())}",
                "",
                _text(analysis.overview, 1_500),
            ]
        )
        for finding in analysis.findings:
            resources = ", ".join(f"`{_text(item, 250)}`" for item in finding.resources)
            ai_lines.extend(
                [
                    "",
                    f"#### {_text(finding.severity.value.upper())}: {_text(finding.title)}",
                    f"- **Category:** {_text(finding.category)}",
                    f"- **Resources:** {resources or 'Not specified'}",
                    f"- **Evidence:** {_text(finding.evidence)}",
                    f"- **Impact:** {_text(finding.impact)}",
                    f"- **Recommendation:** {_text(finding.recommendation)}",
                    f"- **Confidence:** {_text(finding.confidence.value)}",
                ]
            )
        if analysis.questions:
            ai_lines.extend(["", "#### Questions for the human reviewer"])
            ai_lines.extend(f"- {_text(question)}" for question in analysis.questions)

    close = ["", "</details>", "", f"> {_text(DISCLAIMER, 1_000)}", ""]
    prefix = "\n".join(header + deterministic_lines + ai_lines)
    suffix = "\n".join(close)
    if len(prefix) + len(suffix) <= max_chars:
        return prefix + suffix

    notice = "\n\n_The advisory section was truncated to fit the GitHub comment limit._"
    available = max(0, max_chars - len(suffix) - len(notice))
    shortened = prefix[:available]
    if "\n" in shortened:
        shortened = shortened.rsplit("\n", maxsplit=1)[0]
    return shortened + notice + suffix
