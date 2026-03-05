"""Markdown export for Confluence publishing."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

_SEVERITY_ORDER = {"must": 0, "should": 1, "may": 2}
_SEVERITY_BADGE = {"must": "MUST", "should": "SHOULD", "may": "MAY"}


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a Markdown table from headers and rows."""
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _escape(text: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ")


def format_guardrail_list_md(guardrails: list, total: int) -> str:
    """Format guardrails as a Markdown table."""
    headers = ["ID", "Title", "Status", "Severity", "Scope", "Owner"]
    rows = []
    for g in guardrails:
        rows.append([
            g.id[:8],
            _escape(g.title),
            g.status,
            g.severity,
            ", ".join(g.scope),
            _escape(g.owner),
        ])
    table = _md_table(headers, rows)
    return f"{table}\n\n*{total} total*\n"


def format_export_md(guardrails: list, references: list) -> str:
    """Full Confluence-style export of all guardrails."""
    parts: list[str] = []

    # Title
    parts.append("# Architecture Guardrails\n")

    # Summary table
    status_counts: dict[str, int] = defaultdict(int)
    severity_counts: dict[str, int] = defaultdict(int)
    for g in guardrails:
        status_counts[g.status] += 1
        severity_counts[g.severity] += 1

    parts.append("## Summary\n")
    summary_headers = ["Metric", "Count"]
    summary_rows: list[list[str]] = []
    for status in ["active", "draft", "deprecated", "superseded"]:
        if status_counts.get(status):
            summary_rows.append([f"Status: {status}", str(status_counts[status])])
    for severity in ["must", "should", "may"]:
        if severity_counts.get(severity):
            summary_rows.append([f"Severity: {severity}", str(severity_counts[severity])])
    summary_rows.append(["**Total**", f"**{len(guardrails)}**"])
    parts.append(_md_table(summary_headers, summary_rows))
    parts.append("")

    # Build reference lookup
    ref_by_gid: dict[str, list] = defaultdict(list)
    for ref in references:
        ref_by_gid[ref.guardrail_id].append(ref)

    # Group by scope
    scope_groups: dict[str, list] = defaultdict(list)
    for g in guardrails:
        for s in g.scope:
            scope_groups[s].append(g)

    today = date.today()

    for scope_name in sorted(scope_groups):
        parts.append(f"## {scope_name}\n")

        # Sort by severity
        scope_guardrails = sorted(
            scope_groups[scope_name],
            key=lambda g: _SEVERITY_ORDER.get(g.severity, 99),
        )

        for g in scope_guardrails:
            badge = f"**[{_SEVERITY_BADGE.get(g.severity, g.severity)}]**"
            parts.append(f"### {badge} {_escape(g.title)}\n")

            # Review date warning
            if g.review_date:
                rd = date.fromisoformat(g.review_date)
                if rd < today:
                    days = (today - rd).days
                    msg = f"> :warning: Review overdue by {days} days (due {g.review_date})"
                    parts.append(f"{msg}\n")
                else:
                    parts.append(f"> Review date: {g.review_date}\n")

            parts.append(f"**Status:** {g.status} | **Owner:** {_escape(g.owner)}\n")

            parts.append("**Guidance:**\n")
            parts.append(f"{g.guidance}\n")

            parts.append("**Rationale:**\n")
            parts.append(f"{g.rationale}\n")

            if g.exceptions:
                parts.append("**Exceptions:**\n")
                parts.append(f"{g.exceptions}\n")

            # References for this guardrail
            grefs = ref_by_gid.get(g.id, [])
            if grefs:
                parts.append("**References:**\n")
                for ref in grefs:
                    url_part = f" — [{ref.ref_url}]({ref.ref_url})" if ref.ref_url else ""
                    parts.append(f"- [{ref.ref_type}] {_escape(ref.ref_title)}{url_part}")
                    if ref.excerpt:
                        parts.append(f"  > {_escape(ref.excerpt)}")
                parts.append("")

    return "\n".join(parts) + "\n"


def format_guardrail_detail_md(guardrail, refs: list, links: list) -> str:
    """Format a single guardrail with full detail in Markdown."""
    g = guardrail
    parts: list[str] = []

    badge = f"**[{_SEVERITY_BADGE.get(g.severity, g.severity)}]**"
    parts.append(f"## {badge} {_escape(g.title)}\n")
    parts.append(f"**ID:** `{g.id}`\n")
    parts.append(
        f"**Status:** {g.status} | **Severity:** {g.severity} "
        f"| **Owner:** {_escape(g.owner)}\n"
    )
    parts.append(f"**Scope:** {', '.join(g.scope)}\n")
    parts.append(f"**Applies to:** {', '.join(g.applies_to)}\n")
    if g.review_date:
        today = date.today()
        rd = date.fromisoformat(g.review_date)
        if rd < today:
            days = (today - rd).days
            parts.append(
                f"> :warning: Review overdue by {days} days"
                f" (due {g.review_date})\n"
            )
        else:
            parts.append(f"> Review date: {g.review_date}\n")

    parts.append("**Guidance:**\n")
    parts.append(f"{g.guidance}\n")
    parts.append("**Rationale:**\n")
    parts.append(f"{g.rationale}\n")

    if g.exceptions:
        parts.append("**Exceptions:**\n")
        parts.append(f"{g.exceptions}\n")

    if g.consequences:
        parts.append("**Consequences:**\n")
        parts.append(f"{g.consequences}\n")

    if refs:
        parts.append("**References:**\n")
        for ref in refs:
            url_part = ""
            if ref.ref_url:
                url_part = f" — [{ref.ref_url}]({ref.ref_url})"
            parts.append(
                f"- [{ref.ref_type}] {_escape(ref.ref_title)}{url_part}"
            )
        parts.append("")

    if links:
        parts.append("**Links:**\n")
        for lnk in links:
            note_part = f" — {lnk.note}" if lnk.note else ""
            parts.append(
                f"- {lnk.rel_type}: `{lnk.from_id[:8]}` -> "
                f"`{lnk.to_id[:8]}`{note_part}"
            )
        parts.append("")

    return "\n".join(parts) + "\n"


def format_stats_md(stats_dict: dict) -> str:
    """Format statistics as Markdown tables."""
    parts: list[str] = []
    parts.append(f"**Total guardrails:** {stats_dict.get('total', 0)}\n")

    by_status = stats_dict.get("by_status", {})
    if by_status:
        parts.append("### By Status\n")
        parts.append(_md_table(["Status", "Count"], [[s, str(c)] for s, c in by_status.items()]))
        parts.append("")

    by_severity = stats_dict.get("by_severity", {})
    if by_severity:
        parts.append("### By Severity\n")
        rows = [[s, str(c)] for s, c in by_severity.items()]
        parts.append(_md_table(["Severity", "Count"], rows))
        parts.append("")

    by_scope = stats_dict.get("by_scope", {})
    if by_scope:
        parts.append("### By Scope\n")
        parts.append(_md_table(["Scope", "Count"], [[s, str(c)] for s, c in by_scope.items()]))
        parts.append("")

    stale = stats_dict.get("stale", 0)
    parts.append(f"**Stale (review overdue):** {stale}\n")

    return "\n".join(parts)


def format_review_due_md(guardrails: list, cutoff: str) -> str:
    """Format overdue reviews as a Markdown table."""
    today = date.fromisoformat(cutoff)
    headers = ["ID", "Title", "Review Date", "Days Overdue"]
    rows = []
    for g in guardrails:
        review = g.review_date or ""
        if review:
            rd = date.fromisoformat(review)
            days_overdue = (today - rd).days
        else:
            days_overdue = 0
        rows.append([g.id[:8], _escape(g.title), review, str(days_overdue)])

    table = _md_table(headers, rows)
    return f"## Reviews Due\n\n{table}\n"
