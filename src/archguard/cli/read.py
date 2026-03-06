"""Read commands: search, get, related, list, check."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from archguard.cli import app, handle_error, state
from archguard.output.json import envelope


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query text")],
    status: Annotated[str | None, typer.Option("--status", help="Filter by status")] = None,
    severity: Annotated[str | None, typer.Option("--severity", help="Filter by severity")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Filter by scope")] = None,
    applies_to: Annotated[
        str | None, typer.Option("--applies-to", help="Filter by applies_to")
    ] = None,
    lifecycle_stage: Annotated[
        str | None, typer.Option("--lifecycle-stage", help="Filter by lifecycle stage")
    ] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Filter by owner")] = None,
    top: Annotated[int, typer.Option("--top", help="Max results to return")] = 10,
    min_score: Annotated[
        float, typer.Option("--min-score", help="Minimum RRF score threshold (default 0.005)")
    ] = 0.005,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Hybrid BM25 + vector search across guardrails, ranked by RRF."""
    if explain:
        sys.stderr.write(
            "search performs hybrid retrieval: BM25 keyword search via FTS5 and cosine similarity "
            "via Model2Vec embeddings. Results are merged using Reciprocal Rank Fusion (RRF). "
            "Returns compact summaries for triage.\n"
        )
        raise SystemExit(0)

    if not query.strip():
        handle_error("search", "ERR_VALIDATION_INPUT", "Search query must not be empty")

    from archguard.core.index import ensure_index
    from archguard.core.search import hybrid_search

    data_dir = Path(state.data_dir)
    db_path = ensure_index(data_dir)

    # Try to load model for vector search (graceful None if missing)
    model = _try_load_model(data_dir)

    filters = _build_filters(status, severity, scope, applies_to, lifecycle_stage, owner)

    results, total = hybrid_search(
        db_path, query, model=model, filters=filters, top=top, min_score=min_score,
    )

    result_payload = {
        "results": [r.model_dump() for r in results],
        "total": total,
        "query": query,
        "filters_applied": {k: v for k, v in filters.items() if v is not None} if filters else {},
    }

    if state.format == "table":
        from archguard.output.table import format_search_results
        sys.stdout.write(format_search_results(results, total, query))
    elif state.format == "markdown":
        from archguard.output.markdown import format_search_results_md
        sys.stdout.write(format_search_results_md(results, total, query))
    else:
        sys.stdout.write(envelope("search", result_payload) + "\n")


@app.command()
def get(
    guardrail_id: Annotated[str, typer.Argument(help="ULID of the guardrail")],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Get full detail for a guardrail including references and links."""
    if explain:
        sys.stderr.write(
            "get returns the complete guardrail record with all references and linked guardrails.\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails, load_links, load_references

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)

    guardrail = next((g for g in guardrails if g.id == guardrail_id), None)
    if guardrail is None:
        handle_error("get", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found")
        return

    refs_list = load_references(data_dir)
    links_list = load_links(data_dir)
    refs = [r for r in refs_list if r.guardrail_id == guardrail_id]
    links = [
        lnk
        for lnk in links_list
        if lnk.from_id == guardrail_id or lnk.to_id == guardrail_id
    ]

    if state.format == "table":
        from archguard.output.table import format_guardrail_detail
        sys.stdout.write(format_guardrail_detail(guardrail, refs, links))
    elif state.format == "markdown":
        from archguard.output.markdown import format_guardrail_detail_md
        sys.stdout.write(format_guardrail_detail_md(guardrail, refs, links))
    else:
        ref_dicts = [r.model_dump() for r in refs]
        link_dicts = [lnk.model_dump() for lnk in links]
        payload = {
            "guardrail": guardrail.model_dump(),
            "references": ref_dicts,
            "links": link_dicts,
        }
        sys.stdout.write(envelope("get", payload) + "\n")


@app.command()
def related(
    guardrail_id: Annotated[str, typer.Argument(help="ULID of the guardrail")],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Show linked guardrails with relationship types."""
    if explain:
        sys.stderr.write(
            "related returns all guardrails connected to the given guardrail via links, "
            "including the relationship type and direction.\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails, load_links

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)
    links = load_links(data_dir)

    # Verify target guardrail exists
    target = next((g for g in guardrails if g.id == guardrail_id), None)
    if target is None:
        handle_error("related", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found")
        return

    # Build a lookup map
    guardrail_map = {g.id: g for g in guardrails}

    related_items: list[dict[str, str]] = []
    for lnk in links:
        if lnk.from_id == guardrail_id:
            other = guardrail_map.get(lnk.to_id)
            if other:
                related_items.append({
                    "id": other.id,
                    "title": other.title,
                    "status": other.status,
                    "severity": other.severity,
                    "rel_type": lnk.rel_type,
                    "direction": "outgoing",
                    "note": lnk.note,
                })
        elif lnk.to_id == guardrail_id:
            other = guardrail_map.get(lnk.from_id)
            if other:
                related_items.append({
                    "id": other.id,
                    "title": other.title,
                    "status": other.status,
                    "severity": other.severity,
                    "rel_type": lnk.rel_type,
                    "direction": "incoming",
                    "note": lnk.note,
                })

    sys.stdout.write(
        envelope("related", {
            "guardrail_id": guardrail_id,
            "related": related_items,
        })
        + "\n"
    )


@app.command(name="list")
def list_guardrails(
    status: Annotated[str | None, typer.Option("--status", help="Filter by status")] = None,
    severity: Annotated[str | None, typer.Option("--severity", help="Filter by severity")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Filter by scope")] = None,
    applies_to: Annotated[
        str | None, typer.Option("--applies-to", help="Filter by applies_to")
    ] = None,
    lifecycle_stage: Annotated[
        str | None, typer.Option("--lifecycle-stage", help="Filter by lifecycle stage")
    ] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Filter by owner")] = None,
    review_before: Annotated[
        str | None, typer.Option("--review-before", help="Filter by review date")
    ] = None,
    top: Annotated[int, typer.Option("--top", help="Max results to return")] = 50,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """List guardrails with optional filters (no full-text search)."""
    if explain:
        sys.stderr.write(
            "list returns guardrails matching the given filters "
            "without performing full-text search. "
            "Use 'search' for text-based retrieval.\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)

    # Apply filters
    if status is not None:
        guardrails = [g for g in guardrails if g.status == status]
    if severity is not None:
        guardrails = [g for g in guardrails if g.severity == severity]
    if scope is not None:
        guardrails = [g for g in guardrails if scope in g.scope]
    if applies_to is not None:
        guardrails = [g for g in guardrails if applies_to in g.applies_to]
    if lifecycle_stage is not None:
        guardrails = [g for g in guardrails if lifecycle_stage in g.lifecycle_stage]
    if owner is not None:
        guardrails = [g for g in guardrails if g.owner == owner]
    if review_before is not None:
        guardrails = [
            g for g in guardrails if g.review_date is not None and g.review_date < review_before
        ]

    total = len(guardrails)
    guardrails = guardrails[:top]

    if state.format == "table":
        from archguard.output.table import format_guardrail_list
        sys.stdout.write(format_guardrail_list(guardrails, total))
    elif state.format == "markdown":
        from archguard.output.markdown import format_guardrail_list_md
        sys.stdout.write(format_guardrail_list_md(guardrails, total))
    else:
        sys.stdout.write(
            envelope(
                "list",
                {
                    "guardrails": [g.model_dump() for g in guardrails],
                    "returned": len(guardrails),
                    "total": total,
                },
            )
            + "\n"
        )


@app.command()
def check(
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
    schema: Annotated[bool, typer.Option("--schema", help="Print input JSON schema")] = False,
) -> None:
    """Check a proposed decision against the guardrail corpus. Reads context JSON from stdin."""
    if explain:
        sys.stderr.write(
            "check reads a context JSON from stdin describing a proposed "
            "architectural decision, performs deterministic matching "
            "(FTS on text + filter intersection on structured fields), "
            "and returns matching guardrails grouped by severity. "
            "The CLI does not judge compliance; it surfaces relevance.\n"
        )
        raise SystemExit(0)
    if schema:
        from archguard.core.models import CheckContext

        schema_data = CheckContext.model_json_schema()
        sys.stdout.write(envelope("check", {"schema": schema_data}) + "\n")
        raise SystemExit(0)

    import orjson

    from archguard.core.index import ensure_index
    from archguard.core.search import hybrid_search

    data_dir = Path(state.data_dir)

    # Read context from stdin
    raw = sys.stdin.read()
    try:
        context = orjson.loads(raw)
    except Exception:
        handle_error("check", "ERR_VALIDATION_JSON", "Invalid JSON on stdin")
        return

    # Validate required field
    decision = context.get("decision")
    if not decision or not isinstance(decision, str):
        handle_error(
            "check", "ERR_VALIDATION_INPUT",
            "Field 'decision' is required and must be a string",
        )
        return

    # Build search query from decision + tags
    raw_tags: list[str] = context.get("tags") or []
    query_parts: list[str] = [decision]
    if raw_tags:
        query_parts.extend(raw_tags)
    query = " ".join(query_parts)

    # Build filters from structured fields
    filters: dict[str, str | list[str] | None] = {}
    if context.get("scope") and isinstance(context["scope"], list) and context["scope"]:
        filters["scope"] = context["scope"]
    if (
        context.get("applies_to")
        and isinstance(context["applies_to"], list)
        and context["applies_to"]
    ):
        filters["applies_to"] = context["applies_to"]
    if context.get("lifecycle_stage") and isinstance(context["lifecycle_stage"], str):
        filters["lifecycle_stage"] = context["lifecycle_stage"]

    db_path = ensure_index(data_dir)
    model = _try_load_model(data_dir)

    results, _total = hybrid_search(db_path, query, model=model, filters=filters or None, top=50)

    # Build summary: count by severity
    summary: dict[str, int] = {"must": 0, "should": 0, "may": 0}
    for r in results:
        if r.severity in summary:
            summary[r.severity] += 1

    result_payload = {
        "context": context,
        "matches": [r.model_dump() for r in results],
        "summary": summary,
    }
    sys.stdout.write(envelope("check", result_payload) + "\n")


def _try_load_model(data_dir: Path) -> Any:
    """Try to load the Model2Vec model; return None if unavailable."""
    from archguard.core.embeddings import try_load_model

    return try_load_model(data_dir)


def _build_filters(
    status: str | None,
    severity: str | None,
    scope: str | None,
    applies_to: str | None,
    lifecycle_stage: str | None,
    owner: str | None,
) -> dict[str, str | list[str] | None] | None:
    """Build a filters dict from CLI options, or None if no filters."""
    filters: dict[str, str | list[str] | None] = {
        "status": status,
        "severity": severity,
        "scope": scope,
        "applies_to": applies_to,
        "lifecycle_stage": lifecycle_stage,
        "owner": owner,
    }
    if any(v is not None for v in filters.values()):
        return filters
    return None
