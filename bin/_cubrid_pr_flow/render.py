"""Korean Discord card renderer for cubrid-pr-flow notifications."""

from __future__ import annotations

DISCORD_SAFE_MAX_LEN = 1900

KIND_BADGES = {
    "ci_failed": "[CI 실패]",
    "ci_analyzed": "[CI 원인 분석]",
    "review_failed": "[코드 리뷰 실패]",
    "review_passed": "[코드 리뷰 통과]",
    "ask_open_pr": "[PR Open 확인]",
    "ask_rerun_ci": "[CI 재실행 확인]",
    "ask_draft_jira": "[신규 버그 초안 확인]",
    "ask_publish_jira": "[JIRA 발행 확인]",
    "action_result": "[액션 결과]",
    "tc_wait_timeout": "[TC 브랜치 대기 초과]",
    "generic": "[알림]",
}


def render_card(
    *,
    kind: str,
    title: str,
    summary: str = "",
    pr_number: int | None = None,
    head_sha: str = "",
    ticket: str = "",
    repo: str = "CUBRID/cubrid",
    report_url: str = "",
    comment_url: str = "",
    question: str = "",
    action_code: str = "",
    probable_causes: list[str] | None = None,
) -> str:
    """Render a compact Korean Markdown notification card bounded to 1900 characters."""
    badge = KIND_BADGES.get(kind, "[알림]")
    header = f"**{badge} {title.strip()}**"

    meta_parts: list[str] = []
    if pr_number:
        meta_parts.append(f"PR: https://github.com/{repo}/pull/{pr_number}")
    if head_sha:
        meta_parts.append(f"Commit: `{head_sha[:10]}`")
    if ticket:
        meta_parts.append(f"Ticket: {ticket}")
    meta_line = " | ".join(meta_parts)

    link_lines: list[str] = []
    if report_url:
        link_lines.append(f"리포트: {report_url}")
    if comment_url:
        link_lines.append(f"댓글: {comment_url}")

    footer_lines: list[str] = []
    if question:
        footer_lines.append(f"질문: {question.strip()}")
    if action_code:
        footer_lines.append(f"진행하려면 `{action_code}`로 답장해 주세요.")

    body_parts: list[str] = []
    if summary.strip():
        body_parts.append(summary.strip())
    if probable_causes:
        causes = [f"- {item.strip()}" for item in probable_causes if str(item).strip()]
        if causes:
            body_parts.append("추정 원인:\n" + "\n".join(causes))
    body_text = "\n\n".join(body_parts)

    fixed_sections = [header]
    if meta_line:
        fixed_sections.append(meta_line)
    if link_lines:
        fixed_sections.append("\n".join(link_lines))
    if footer_lines:
        fixed_sections.append("\n".join(footer_lines))

    fixed_without_body = "\n".join(fixed_sections)
    if not body_text:
        return fixed_without_body[:DISCORD_SAFE_MAX_LEN]

    # Reserve room for header + meta + links + footer so links and ACT code are never truncated.
    separator_overhead = 4
    available_for_body = DISCORD_SAFE_MAX_LEN - len(fixed_without_body) - separator_overhead
    if available_for_body < 40:
        # Extreme fallback if links/header alone consume almost the entire budget.
        trimmed_body = body_text[: max(0, available_for_body)]
    elif len(body_text) > available_for_body:
        trimmed_body = body_text[: available_for_body - 3].rstrip() + "..."
    else:
        trimmed_body = body_text

    assembled: list[str] = [header]
    if meta_line:
        assembled.append(meta_line)
    if trimmed_body:
        assembled.append("")
        assembled.append(trimmed_body)
    if link_lines:
        assembled.append("")
        assembled.extend(link_lines)
    if footer_lines:
        assembled.append("")
        assembled.extend(footer_lines)
    return "\n".join(assembled)
