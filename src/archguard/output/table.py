"""Rich table output for human-readable display."""

from __future__ import annotations

from datetime import date
from io import StringIO
from typing import Any

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from archguard.core.models import Guardrail, Link, Reference, SearchResult


def _severity_style(severity: str) -> str:
    return {"must": "bold red", "should": "yellow", "may": "green"}.get(severity, "")


def _status_style(status: str) -> str:
    return {
        "active": "green",
        "deprecated": "dim",
        "superseded": "strike",
    }.get(status, "")


def _capture(renderable: RenderableType) -> str:

    from archguard.output.json import is_interactive, is_llm_mode

    sio = StringIO()
    # Respect isatty() and LLM=true: only force color when stdout is a real terminal
    use_color = is_interactive() and not is_llm_mode()
    console = Console(file=sio, force_terminal=use_color, width=120, no_color=not use_color)
    console.print(renderable)
    return sio.getvalue()


def format_guardrail_list(guardrails: list[Guardrail], total: int) -> str:
    """Format a list of guardrails as a Rich table."""
    table = Table(title="Guardrails", show_lines=False)
    table.add_column("ID", style="cyan", max_width=8)
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Scope")
    table.add_column("Owner")

    for g in guardrails:
        status_text = Text(g.status, style=_status_style(g.status))
        severity_text = Text(g.severity, style=_severity_style(g.severity))
        table.add_row(
            g.id[:8],
            g.title,
            status_text,
            severity_text,
            ", ".join(g.scope),
            g.owner,
        )

    table.add_section()
    table.add_row("", f"[bold]{total}[/bold] total", "", "", "", "")

    return _capture(table)


def format_search_results(
    results: list[SearchResult], total: int, query: str
) -> str:
    """Format search results as a Rich table."""
    table = Table(title=f"Search: [italic]{query}[/italic]", show_lines=False)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Score", justify="right")
    table.add_column("Sources")

    for rank, r in enumerate(results, 1):
        severity_text = Text(r.severity, style=_severity_style(r.severity))
        status_text = Text(r.status, style=_status_style(r.status))
        title = r.title
        if r.superseded_by:
            title = f"{title} (superseded by {r.superseded_by[:8]})"
        table.add_row(
            str(rank),
            title,
            status_text,
            severity_text,
            f"{r.score:.2f}",
            ", ".join(r.match_sources),
        )

    table.add_section()
    table.add_row("", f"[bold]{total}[/bold] total", "", "", "", "")

    return _capture(table)


def format_stats(stats_dict: dict[str, Any]) -> str:
    """Format statistics as a Rich panel with grouped counts."""
    lines: list[str] = []
    lines.append(f"[bold]Total guardrails:[/bold] {stats_dict.get('total', 0)}")
    lines.append("")

    by_status: dict[str, int] = stats_dict.get("by_status", {})
    if by_status:
        lines.append("[bold underline]By Status[/bold underline]")
        for status, count in by_status.items():
            style = _status_style(status)
            label = f"[{style}]{status}[/{style}]" if style else status
            lines.append(f"  {label}: {count}")
        lines.append("")

    by_severity: dict[str, int] = stats_dict.get("by_severity", {})
    if by_severity:
        lines.append("[bold underline]By Severity[/bold underline]")
        for severity, count in by_severity.items():
            style = _severity_style(severity)
            label = f"[{style}]{severity}[/{style}]" if style else severity
            lines.append(f"  {label}: {count}")
        lines.append("")

    by_scope: dict[str, int] = stats_dict.get("by_scope", {})
    if by_scope:
        lines.append("[bold underline]By Scope[/bold underline]")
        for scope, count in by_scope.items():
            lines.append(f"  {scope}: {count}")
        lines.append("")

    stale: int = stats_dict.get("stale", 0)
    lines.append(f"[bold]Stale (review overdue):[/bold] {stale}")

    panel = Panel("\n".join(lines), title="Guardrail Statistics", border_style="blue")
    return _capture(panel)


def format_review_due(guardrails: list[Guardrail], cutoff: str) -> str:
    """Format guardrails with overdue reviews as a Rich table."""
    today = date.fromisoformat(cutoff)
    table = Table(title="Reviews Due", show_lines=False)
    table.add_column("ID", style="cyan", max_width=8)
    table.add_column("Title")
    table.add_column("Review Date")
    table.add_column("Days Overdue", justify="right", style="red")

    for g in guardrails:
        review = g.review_date or ""
        if review:
            rd = date.fromisoformat(review)
            days_overdue = (today - rd).days
        else:
            days_overdue = 0

        table.add_row(
            g.id[:8],
            g.title,
            review,
            str(days_overdue),
        )

    return _capture(table)


def format_guardrail_detail(
    guardrail: Guardrail, refs: list[Reference], links: list[Link]
) -> str:
    """Format a single guardrail with full detail, refs, and links."""
    g = guardrail
    lines: list[str] = []

    sev_style = _severity_style(g.severity)
    stat_style = _status_style(g.status)

    lines.append(f"[bold]{g.title}[/bold]")
    lines.append("")
    lines.append(f"[dim]ID:[/dim]       {g.id}")
    if stat_style:
        lines.append(f"[dim]Status:[/dim]   [{stat_style}]{g.status}[/{stat_style}]")
    else:
        lines.append(f"[dim]Status:[/dim]   {g.status}")
    if sev_style:
        lines.append(f"[dim]Severity:[/dim] [{sev_style}]{g.severity}[/{sev_style}]")
    else:
        lines.append(f"[dim]Severity:[/dim] {g.severity}")
    lines.append(f"[dim]Scope:[/dim]    {', '.join(g.scope)}")
    lines.append(f"[dim]Applies to:[/dim] {', '.join(g.applies_to)}")
    lines.append(f"[dim]Owner:[/dim]    {g.owner}")
    if g.review_date:
        lines.append(f"[dim]Review:[/dim]   {g.review_date}")
    lines.append(f"[dim]Created:[/dim]  {g.created_at}")
    lines.append(f"[dim]Updated:[/dim]  {g.updated_at}")
    lines.append("")

    lines.append("[bold underline]Guidance[/bold underline]")
    lines.append(g.guidance)
    lines.append("")

    lines.append("[bold underline]Rationale[/bold underline]")
    lines.append(g.rationale)

    if g.exceptions:
        lines.append("")
        lines.append("[bold underline]Exceptions[/bold underline]")
        lines.append(g.exceptions)

    if g.consequences:
        lines.append("")
        lines.append("[bold underline]Consequences[/bold underline]")
        lines.append(g.consequences)

    if g.metadata:
        lines.append("")
        lines.append("[bold underline]Metadata[/bold underline]")
        for mk, mv in g.metadata.items():
            lines.append(f"  {mk}: {mv}")

    if refs:
        lines.append("")
        lines.append("[bold underline]References[/bold underline]")
        for r in refs:
            url_part = f" ({r.ref_url})" if r.ref_url else ""
            lines.append(f"  [{r.ref_type}] {r.ref_title}{url_part}")
            if r.excerpt:
                lines.append(f"    {r.excerpt}")

    if links:
        lines.append("")
        lines.append("[bold underline]Links[/bold underline]")
        for lnk in links:
            note_part = f" - {lnk.note}" if lnk.note else ""
            lines.append(
                f"  {lnk.rel_type}: {lnk.from_id[:8]} -> {lnk.to_id[:8]}{note_part}"
            )

    panel = Panel("\n".join(lines), border_style="blue")
    return _capture(panel)
