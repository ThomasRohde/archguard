"""Export commands: export."""

from __future__ import annotations

import csv
import io
import sys
from typing import Annotated

import orjson
import typer

from archguard.cli import app, handle_error, require_data_dir
from archguard.output.json import envelope, is_llm_mode


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
        sys.stderr.write(
            "export produces filtered guardrails in the requested format. "
            "json is a full-fidelity snapshot including guardrails, references, and links "
            "for backup or transfer. csv and markdown are publishing views focused on "
            "guardrail records.\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails, load_links, load_references

    data_dir = require_data_dir("export")
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
        guardrail_ids = {g.id for g in guardrails}
        references = [
            r.model_dump()
            for r in load_references(data_dir)
            if r.guardrail_id in guardrail_ids
        ]
        links = [
            link.model_dump()
            for link in load_links(data_dir)
            if link.from_id in guardrail_ids and link.to_id in guardrail_ids
        ]
        sys.stdout.write(
            envelope(
                "export",
                {
                    "fidelity": "full",
                    "guardrails": [g.model_dump() for g in guardrails],
                    "references": references,
                    "links": links,
                },
            )
            + "\n"
        )
    elif format == "csv":
        buf = io.StringIO()
        columns = [
            "id", "title", "status", "severity", "rationale", "guidance",
            "exceptions", "consequences", "scope", "applies_to",
            "lifecycle_stage", "owner", "review_date", "superseded_by",
            "created_at", "updated_at", "metadata",
        ]
        writer = csv.DictWriter(buf, fieldnames=columns)
        writer.writeheader()
        for g in guardrails:
            writer.writerow({
                "id": g.id,
                "title": g.title,
                "status": g.status,
                "severity": g.severity,
                "rationale": g.rationale,
                "guidance": g.guidance,
                "exceptions": g.exceptions,
                "consequences": g.consequences,
                "scope": ";".join(g.scope),
                "applies_to": ";".join(g.applies_to),
                "lifecycle_stage": ";".join(g.lifecycle_stage),
                "owner": g.owner,
                "review_date": g.review_date or "",
                "superseded_by": g.superseded_by or "",
                "created_at": g.created_at,
                "updated_at": g.updated_at,
                "metadata": "" if not g.metadata else orjson.dumps(g.metadata).decode(),
            })
        content = buf.getvalue()
        if is_llm_mode():
            sys.stdout.write(
                envelope("export", {"content": content, "format": "csv"}) + "\n"
            )
        else:
            sys.stdout.write(content)
    elif format == "markdown":
        from archguard.output.markdown import format_export_md
        references = load_references(data_dir)
        content = format_export_md(guardrails, references)
        if is_llm_mode():
            sys.stdout.write(
                envelope("export", {"content": content, "format": "markdown"}) + "\n"
            )
        else:
            sys.stdout.write(content)
    else:
        handle_error("export", "ERR_VALIDATION_FORMAT", f"Unknown format: {format}")
