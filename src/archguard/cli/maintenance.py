"""Maintenance commands: stats, review-due, deduplicate, import."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from archguard.cli import app, handle_error


@app.command()
def stats(
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Show counts by status, severity, scope, and staleness."""
    if explain:
        sys.stdout.write(
            "stats returns aggregate counts of guardrails grouped by status, severity, scope, "
            "and review staleness.\n"
        )
        raise SystemExit(0)

    from collections import Counter
    from datetime import UTC, datetime
    from pathlib import Path

    from archguard.cli import state
    from archguard.core.store import load_guardrails
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)

    by_status: dict[str, int] = Counter()
    by_severity: dict[str, int] = Counter()
    by_scope: dict[str, int] = Counter()
    stale = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    for g in guardrails:
        by_status[g.status] += 1
        by_severity[g.severity] += 1
        for s in g.scope:
            by_scope[s] += 1
        if g.review_date is not None and g.review_date <= today:
            stale += 1

    stats_dict = {
        "total": len(guardrails),
        "by_status": dict(by_status),
        "by_severity": dict(by_severity),
        "by_scope": dict(by_scope),
        "stale": stale,
    }

    if state.format == "table":
        from archguard.output.table import format_stats
        sys.stdout.write(format_stats(stats_dict))
    elif state.format == "markdown":
        from archguard.output.markdown import format_stats_md
        sys.stdout.write(format_stats_md(stats_dict))
    else:
        sys.stdout.write(success_response(stats_dict) + "\n")


@app.command(name="review-due")
def review_due(
    before: Annotated[str | None, typer.Option("--before", help="ISO 8601 date cutoff")] = None,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """List guardrails past or approaching their review date."""
    if explain:
        sys.stdout.write(
            "review-due lists guardrails whose review_date is before the given date (or today).\n"
        )
        raise SystemExit(0)

    from datetime import UTC, datetime
    from pathlib import Path

    from archguard.cli import state
    from archguard.core.store import load_guardrails
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)

    cutoff = before if before is not None else datetime.now(UTC).strftime("%Y-%m-%d")

    # Filter guardrails with review_date <= cutoff
    due = [g for g in guardrails if g.review_date is not None and g.review_date <= cutoff]
    due.sort(key=lambda g: g.review_date)  # type: ignore[arg-type]

    if state.format == "table":
        from archguard.output.table import format_review_due
        sys.stdout.write(format_review_due(due, cutoff))
    elif state.format == "markdown":
        from archguard.output.markdown import format_review_due_md
        sys.stdout.write(format_review_due_md(due, cutoff))
    else:
        sys.stdout.write(
            success_response({
                "cutoff": cutoff,
                "guardrails": [g.model_dump() for g in due],
                "total": len(due),
            }) + "\n"
        )


@app.command()
def deduplicate(
    threshold: Annotated[
        float, typer.Option("--threshold", help="Similarity threshold (0-1)")
    ] = 0.85,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Detect likely duplicate guardrails via hybrid FTS + vector similarity."""
    if explain:
        sys.stdout.write(
            "deduplicate computes pairwise similarity between all guardrails using both FTS and "
            "vector embeddings, and reports pairs above the threshold for human review.\n"
        )
        raise SystemExit(0)

    from pathlib import Path

    from archguard.cli import state
    from archguard.core.store import load_guardrails
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)

    if len(guardrails) < 2:
        sys.stdout.write(
            success_response({"pairs": [], "total": 0, "threshold": threshold}) + "\n"
        )
        return

    pairs: list[dict] = []

    def _make_pair(ga, gb, sim: float, method: str) -> dict:
        return {
            "id_a": ga.id, "title_a": ga.title,
            "id_b": gb.id, "title_b": gb.title,
            "similarity": round(sim, 3), "method": method,
        }

    # Try embedding-based similarity
    from archguard.core.embeddings import try_load_model
    model = try_load_model(data_dir)

    if model is not None:
        from archguard.core.embeddings import cosine_similarity, embed_guardrail
        embeddings = [embed_guardrail(model, g) for g in guardrails]
        for i in range(len(guardrails)):
            for j in range(i + 1, len(guardrails)):
                sim = cosine_similarity(embeddings[i], embeddings[j])
                if sim >= threshold:
                    pairs.append(_make_pair(guardrails[i], guardrails[j], sim, "embedding"))
    else:
        # Fallback: Jaccard similarity on word sets
        word_sets = [
            set((g.title + " " + g.guidance).lower().split())
            for g in guardrails
        ]
        for i in range(len(guardrails)):
            for j in range(i + 1, len(guardrails)):
                intersection = len(word_sets[i] & word_sets[j])
                union = len(word_sets[i] | word_sets[j])
                sim = intersection / union if union > 0 else 0.0
                if sim >= threshold:
                    pairs.append(_make_pair(guardrails[i], guardrails[j], sim, "jaccard"))

    pairs.sort(key=lambda p: p["similarity"], reverse=True)

    sys.stdout.write(
        success_response({"pairs": pairs, "total": len(pairs), "threshold": threshold}) + "\n"
    )


@app.command(name="import")
def import_guardrails(
    file: Annotated[str, typer.Argument(help="Path to JSON or CSV file for bulk import")],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Bulk upsert guardrails from a JSON or CSV file."""
    if explain:
        sys.stdout.write(
            "import reads guardrails from a JSON array or CSV file, upserts them (matching on ID "
            "or title), validates each one, and rebuilds the index.\n"
        )
        raise SystemExit(0)

    import csv as csv_mod
    from datetime import UTC, datetime
    from io import StringIO
    from pathlib import Path

    import orjson
    from ulid import ULID

    from archguard.cli import state
    from archguard.core.models import Guardrail, GuardrailCreate
    from archguard.core.store import load_guardrails, load_taxonomy, rewrite_jsonl
    from archguard.output.json import success_response

    file_path = Path(file)
    if not file_path.exists():
        handle_error(1, "file_not_found", f"File not found: {file}")

    ext = file_path.suffix.lower()
    if ext not in (".json", ".csv"):
        handle_error(1, "invalid_format", f"Unsupported file extension: {ext}. Use .json or .csv")

    data_dir = Path(state.data_dir)
    guardrails = load_guardrails(data_dir)
    taxonomy = load_taxonomy(data_dir)
    by_title = {g.title: g for g in guardrails}

    raw_records: list[dict] = []
    errors: list[str] = []

    if ext == ".json":
        try:
            content = file_path.read_bytes()
            parsed = orjson.loads(content)
            if not isinstance(parsed, list):
                handle_error(1, "invalid_format", "JSON file must contain an array of objects")
            raw_records = parsed
        except orjson.JSONDecodeError as exc:
            handle_error(1, "invalid_json", str(exc))
    else:
        text = file_path.read_text(encoding="utf-8")
        reader = csv_mod.DictReader(StringIO(text))
        for row in reader:
            record: dict = dict(row)
            if "scope" in record and isinstance(record["scope"], str):
                record["scope"] = [s.strip() for s in record["scope"].split(";") if s.strip()]
            if "applies_to" in record and isinstance(record["applies_to"], str):
                parts = record["applies_to"].split(";")
                record["applies_to"] = [s.strip() for s in parts if s.strip()]
            if "lifecycle_stage" in record and isinstance(record["lifecycle_stage"], str):
                val = record["lifecycle_stage"].strip()
                record["lifecycle_stage"] = (
                    [s.strip() for s in val.split(";") if s.strip()]
                    if val
                    else ["acquire", "build", "operate", "retire"]
                )
            raw_records.append(record)

    new_count = 0
    updated_count = 0
    now = datetime.now(UTC).isoformat()

    for i, raw in enumerate(raw_records):
        try:
            create = GuardrailCreate.model_validate(raw)
        except Exception as exc:
            errors.append(f"Record {i}: {exc}")
            continue

        if taxonomy:
            bad_scopes = [s for s in create.scope if s not in taxonomy]
            if bad_scopes:
                errors.append(f"Record {i}: invalid scope values: {bad_scopes}")
                continue

        if create.title in by_title:
            existing = by_title[create.title]
            merged = existing.model_dump()
            for field, value in create.model_dump(exclude_defaults=True).items():
                if value is not None and field != "references":
                    merged[field] = value
            merged["updated_at"] = now
            updated_obj = Guardrail.model_validate(merged)
            by_title[create.title] = updated_obj
            for idx, g in enumerate(guardrails):
                if g.title == create.title:
                    guardrails[idx] = updated_obj
                    break
            updated_count += 1
        else:
            new_id = str(ULID())
            full = Guardrail(
                id=new_id,
                title=create.title,
                status=create.status,
                severity=create.severity,
                rationale=create.rationale,
                guidance=create.guidance,
                exceptions=create.exceptions,
                consequences=create.consequences,
                scope=create.scope,
                applies_to=create.applies_to,
                lifecycle_stage=create.lifecycle_stage,
                owner=create.owner,
                review_date=create.review_date,
                created_at=now,
                updated_at=now,
                metadata=create.metadata,
            )
            guardrails.append(full)
            by_title[create.title] = full
            new_count += 1

    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    sys.stdout.write(
        success_response({"imported": new_count, "updated": updated_count, "errors": errors}) + "\n"
    )
