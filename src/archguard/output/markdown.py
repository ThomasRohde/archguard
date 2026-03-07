"""Markdown export for Confluence publishing."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from archguard.core.models import Guardrail, Link, Reference, SearchResult
from archguard.core.public_ids import display_guardrail_id, display_identifier_value

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


def _format_export_link(current_id: str, link: Link, guardrail_map: dict[str, Guardrail]) -> str:
    """Format a relationship entry for the full markdown export."""
    if link.from_id == current_id:
        other_id = link.to_id
        rel_text = f"{link.rel_type} ->"
    else:
        other_id = link.from_id
        rel_text = f"<- {link.rel_type}"

    other = guardrail_map.get(other_id)
    identifier = display_identifier_value(other_id, guardrail_map) or other_id[:8]
    title_part = f" - {_escape(other.title)}" if other else ""
    note_part = f" ({_escape(link.note)})" if link.note else ""
    return f"- {rel_text} `{identifier}`{title_part}{note_part}"


def format_search_results_md(results: list[SearchResult], total: int, query: str) -> str:
    """Format search results as a Markdown table."""
    headers = ["#", "ID", "Title", "Status", "Severity", "Score", "Sources"]
    rows: list[list[str]] = []
    for rank, r in enumerate(results, 1):
        title = r.title
        if r.superseded_by:
            superseded_display = r.superseded_by_public_id or r.superseded_by[:8]
            title = f"{title} (superseded by {superseded_display})"
        rows.append([
            str(rank),
            r.public_id or r.id[:8],
            _escape(title),
            r.status,
            r.severity,
            f"{r.score:.2f}",
            ", ".join(r.match_sources),
        ])
    table = _md_table(headers, rows)
    return f"## Search: {_escape(query)}\n\n{table}\n\n*{total} total*\n"


def format_guardrail_list_md(guardrails: list[Guardrail], total: int) -> str:
    """Format guardrails as a Markdown table."""
    headers = ["ID", "Title", "Status", "Severity", "Scope", "Owner"]
    rows: list[list[str]] = []
    for g in guardrails:
        rows.append([
            display_guardrail_id(g),
            _escape(g.title),
            g.status,
            g.severity,
            ", ".join(g.scope),
            _escape(g.owner),
        ])
    table = _md_table(headers, rows)
    return f"{table}\n\n*{total} total*\n"


def format_export_md(
    guardrails: list[Guardrail],
    references: list[Reference],
    links: list[Link] | None = None,
) -> str:
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
    ref_by_gid: dict[str, list[Reference]] = defaultdict(list)
    for ref in references:
        ref_by_gid[ref.guardrail_id].append(ref)

    guardrail_map = {g.id: g for g in guardrails}
    link_by_gid: dict[str, list[Link]] = defaultdict(list)
    for link in links or []:
        link_by_gid[link.from_id].append(link)
        if link.to_id != link.from_id:
            link_by_gid[link.to_id].append(link)

    # Group by primary scope so multi-scope guardrails are exported once.
    scope_groups: dict[str, list[Guardrail]] = defaultdict(list)
    for g in guardrails:
        scope_groups[g.scope[0]].append(g)

    today = date.today()

    for scope_name in sorted(scope_groups):
        parts.append(f"## {scope_name}\n")

        # Sort by severity
        scope_guardrails = sorted(
            scope_groups[scope_name],
            key=lambda g: (_SEVERITY_ORDER.get(g.severity, 99), g.title.casefold()),
        )

        for g in scope_guardrails:
            badge = f"**[{_SEVERITY_BADGE.get(g.severity, g.severity)}]**"
            parts.append(f"### {badge} {_escape(g.title)}\n")
            if g.public_id:
                parts.append(f"**Public ID:** `{g.public_id}`\n")
            parts.append(f"**Internal ID:** `{g.id}`\n")

            # Review date warning
            if g.review_date:
                rd = date.fromisoformat(g.review_date)
                if rd < today:
                    days = (today - rd).days
                    msg = f"> :warning: Review overdue by {days} days (due {g.review_date})"
                    parts.append(f"{msg}\n")
                else:
                    parts.append(f"> Review date: {g.review_date}\n")

            parts.append(f"**Scope:** {', '.join(g.scope)}\n")
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
                    url_part = f" - [{ref.ref_url}]({ref.ref_url})" if ref.ref_url else ""
                    parts.append(f"- [{ref.ref_type}] {_escape(ref.ref_title)}{url_part}")
                    if ref.excerpt:
                        parts.append(f"  > {_escape(ref.excerpt)}")
                parts.append("")

            glinks = sorted(
                link_by_gid.get(g.id, []),
                key=lambda link: (
                    display_identifier_value(
                        link.to_id if link.from_id == g.id else link.from_id,
                        guardrail_map,
                    )
                    or (link.to_id if link.from_id == g.id else link.from_id)[:8],
                    link.rel_type,
                    link.note,
                ),
            )
            if glinks:
                parts.append("**Links:**\n")
                for link in glinks:
                    parts.append(_format_export_link(g.id, link, guardrail_map))
                parts.append("")

    return "\n".join(parts) + "\n"


def format_guardrail_detail_md(
    guardrail: Guardrail,
    refs: list[Reference],
    links: list[Link],
    guardrail_map: dict[str, Guardrail] | None = None,
) -> str:
    """Format a single guardrail with full detail in Markdown."""
    g = guardrail
    guardrail_map = guardrail_map or {g.id: g}
    parts: list[str] = []

    badge = f"**[{_SEVERITY_BADGE.get(g.severity, g.severity)}]**"
    parts.append(f"## {badge} {_escape(g.title)}\n")
    if g.public_id:
        parts.append(f"**Public ID:** `{g.public_id}`\n")
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
                f"- {lnk.rel_type}: `"
                f"{display_identifier_value(lnk.from_id, guardrail_map) or lnk.from_id[:8]}` -> `"
                f"{display_identifier_value(lnk.to_id, guardrail_map) or lnk.to_id[:8]}`{note_part}"
            )
        parts.append("")

    return "\n".join(parts) + "\n"


def format_stats_md(stats_dict: dict[str, Any]) -> str:
    """Format statistics as Markdown tables."""
    parts: list[str] = []
    parts.append(f"**Total guardrails:** {stats_dict.get('total', 0)}\n")

    by_status: dict[str, int] = stats_dict.get("by_status", {})
    if by_status:
        parts.append("### By Status\n")
        parts.append(
            _md_table(["Status", "Count"], [[s, str(c)] for s, c in by_status.items()])
        )
        parts.append("")

    by_severity: dict[str, int] = stats_dict.get("by_severity", {})
    if by_severity:
        parts.append("### By Severity\n")
        rows: list[list[str]] = [[s, str(c)] for s, c in by_severity.items()]
        parts.append(_md_table(["Severity", "Count"], rows))
        parts.append("")

    by_scope: dict[str, int] = stats_dict.get("by_scope", {})
    if by_scope:
        parts.append("### By Scope\n")
        parts.append(
            _md_table(["Scope", "Count"], [[s, str(c)] for s, c in by_scope.items()])
        )
        parts.append("")

    stale: int = stats_dict.get("stale", 0)
    parts.append(f"**Stale (review overdue):** {stale}\n")

    return "\n".join(parts)


def format_review_due_md(guardrails: list[Guardrail], cutoff: str) -> str:
    """Format overdue reviews as a Markdown table."""
    today = date.fromisoformat(cutoff)
    headers = ["ID", "Title", "Review Date", "Days Overdue"]
    rows: list[list[str]] = []
    for g in guardrails:
        review = g.review_date or ""
        if review:
            rd = date.fromisoformat(review)
            days_overdue = (today - rd).days
        else:
            days_overdue = 0
        rows.append([g.id[:8], _escape(g.title), review, str(days_overdue)])
        rows[-1][0] = display_guardrail_id(g)

    table = _md_table(headers, rows)
    return f"## Reviews Due\n\n{table}\n"
