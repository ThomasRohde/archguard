"""Export commands: export."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import Annotated

import orjson
import typer

from guardrails_cli.cli import app, handle_error, state


@app.command()
def export(
    format: Annotated[
        str, typer.Option("--format", help="Export format: json, csv, markdown")
    ] = "json",
    status: Annotated[str | None, typer.Option("--status", help="Filter by status")] = None,
    severity: Annotated[str | None, typer.Option("--severity", help="Filter by severity")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Filter by scope")] = None,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Export guardrails in JSON, CSV, or Markdown format."""
    if explain:
        sys.stdout.write(
            "export produces filtered guardrails in the requested format. "
            "json for machine consumption, csv for spreadsheets, "
            "markdown for Confluence publishing.\n"
        )
        raise SystemExit(0)

    from guardrails_cli.core.store import load_guardrails

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)

    # Apply filters
    if status is not None:
        guardrails = [g for g in guardrails if g.status == status]
    if severity is not None:
        guardrails = [g for g in guardrails if g.severity == severity]
    if scope is not None:
        guardrails = [g for g in guardrails if scope in g.scope]

    # Dispatch on format
    if format == "json":
        output = orjson.dumps([g.model_dump() for g in guardrails]).decode()
    elif format == "csv":
        buf = io.StringIO()
        columns = [
            "id", "title", "status", "severity", "scope", "applies_to",
            "owner", "review_date", "created_at", "updated_at",
        ]
        writer = csv.DictWriter(buf, fieldnames=columns)
        writer.writeheader()
        for g in guardrails:
            writer.writerow({
                "id": g.id,
                "title": g.title,
                "status": g.status,
                "severity": g.severity,
                "scope": ";".join(g.scope),
                "applies_to": ";".join(g.applies_to),
                "owner": g.owner,
                "review_date": g.review_date or "",
                "created_at": g.created_at,
                "updated_at": g.updated_at,
            })
        output = buf.getvalue()
    elif format == "markdown":
        from guardrails_cli.core.store import load_references
        from guardrails_cli.output.markdown import format_export_md
        references = load_references(data_dir)
        output = format_export_md(guardrails, references)
    else:
        handle_error(20, "invalid_format", f"Unknown format: {format}")
        return

    sys.stdout.write(output)
