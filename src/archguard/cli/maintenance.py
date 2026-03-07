"""Maintenance commands: stats, review-due, deduplicate, import."""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

import typer

from archguard.cli import (
    app,
    emit_index_build_notice,
    ensure_supported_format,
    handle_error,
    require_data_dir,
    state,
    summarize_validation_error,
)
from archguard.core.models import Guardrail
from archguard.core.public_ids import next_public_id
from archguard.core.search_terms import normalize_text
from archguard.output.json import envelope


@app.command()
def stats(
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Show counts by status, severity, scope, and staleness."""
    if explain:
        sys.stderr.write(
            "stats returns aggregate counts of guardrails grouped by status, severity, scope, "
            "and review staleness.\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails

    data_dir = require_data_dir("stats")
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
        sys.stdout.write(envelope("stats", stats_dict) + "\n")


@app.command(name="review-due")
def review_due(
    before: Annotated[
        str | None,
        typer.Option("--before", help="ISO 8601 date cutoff (default: 30 days from today)"),
    ] = None,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """List guardrails past or approaching their review date."""
    if explain:
        sys.stderr.write(
            "review-due lists guardrails whose review_date is before the given date "
            "(default: 30 days from today).\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails

    data_dir = require_data_dir("review-due")
    guardrails = load_guardrails(data_dir)

    default_cutoff = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff = before if before is not None else default_cutoff

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
            envelope("review-due", {
                "cutoff": cutoff,
                "guardrails": [g.model_dump() for g in due],
                "total": len(due),
            })
            + "\n"
        )


@app.command()
def deduplicate(
    threshold: Annotated[
        float, typer.Option("--threshold", help="Similarity threshold (0-1)")
    ] = 0.65,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Detect likely duplicate guardrails via hybrid FTS + vector similarity."""
    if explain:
        sys.stderr.write(
            "deduplicate computes pairwise similarity between all guardrails using both FTS and "
            "vector embeddings, and reports pairs above the threshold for human review. "
            "The default threshold is tuned for short normative guardrails; increase it when you "
            "want fewer suggestions.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("deduplicate", "json")

    from archguard.core.store import load_guardrails

    data_dir = require_data_dir("deduplicate")
    guardrails = load_guardrails(data_dir)

    if len(guardrails) < 2:
        sys.stdout.write(
            envelope("deduplicate", {"pairs": [], "total": 0, "threshold": threshold}) + "\n"
        )
        return

    pairs: list[dict[str, Any]] = []

    def _make_pair(
        ga: Guardrail,
        gb: Guardrail,
        sim: float,
        method: str,
        *,
        lexical_similarity: float | None = None,
        title_similarity: float | None = None,
        embedding_similarity: float | None = None,
        shared_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        pair: dict[str, Any] = {
            "id_a": ga.id, "title_a": ga.title,
            "id_b": gb.id, "title_b": gb.title,
            "similarity": round(sim, 3), "method": method,
        }
        if lexical_similarity is not None:
            pair["lexical_similarity"] = round(lexical_similarity, 3)
        if title_similarity is not None:
            pair["title_similarity"] = round(title_similarity, 3)
        if embedding_similarity is not None:
            pair["embedding_similarity"] = round(embedding_similarity, 3)
        if shared_terms:
            pair["shared_terms"] = shared_terms
        return pair

    def _token_set(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", normalize_text(text)))

    def _jaccard_similarity(left: set[str], right: set[str]) -> float:
        union = len(left | right)
        if union == 0:
            return 0.0
        return len(left & right) / union

    def _duplicate_score(
        lexical_similarity: float,
        title_similarity: float,
        embedding_similarity: float | None,
    ) -> float:
        score = 0.55 * lexical_similarity + 0.25 * title_similarity
        if embedding_similarity is not None:
            score += 0.2 * embedding_similarity
            if embedding_similarity >= 0.85 and lexical_similarity >= 0.25:
                score += 0.1
        if lexical_similarity >= 0.45:
            score += 0.15
        if title_similarity >= 0.45:
            score += 0.1
        return min(score, 1.0)

    # Try embedding-based similarity
    from archguard.core.embeddings import try_load_model
    model = try_load_model(data_dir)
    token_sets = [_token_set(f"{g.title} {g.guidance} {g.rationale}") for g in guardrails]
    title_token_sets = [_token_set(g.title) for g in guardrails]

    if model is not None:
        from archguard.core.embeddings import cosine_similarity, embed_guardrail
        embeddings = [embed_guardrail(model, g) for g in guardrails]
        for i in range(len(guardrails)):
            for j in range(i + 1, len(guardrails)):
                lexical_similarity = _jaccard_similarity(token_sets[i], token_sets[j])
                title_similarity = _jaccard_similarity(title_token_sets[i], title_token_sets[j])
                embedding_similarity = cosine_similarity(embeddings[i], embeddings[j])
                sim = _duplicate_score(
                    lexical_similarity,
                    title_similarity,
                    embedding_similarity,
                )
                if sim >= threshold:
                    pairs.append(
                        _make_pair(
                            guardrails[i],
                            guardrails[j],
                            sim,
                            "hybrid",
                            lexical_similarity=lexical_similarity,
                            title_similarity=title_similarity,
                            embedding_similarity=embedding_similarity,
                            shared_terms=sorted(token_sets[i] & token_sets[j])[:8],
                        )
                    )
    else:
        # Fallback: combine body/title overlap without embeddings.
        for i in range(len(guardrails)):
            for j in range(i + 1, len(guardrails)):
                lexical_similarity = _jaccard_similarity(token_sets[i], token_sets[j])
                title_similarity = _jaccard_similarity(title_token_sets[i], title_token_sets[j])
                sim = _duplicate_score(lexical_similarity, title_similarity, None)
                if sim >= threshold:
                    pairs.append(
                        _make_pair(
                            guardrails[i],
                            guardrails[j],
                            sim,
                            "lexical",
                            lexical_similarity=lexical_similarity,
                            title_similarity=title_similarity,
                            shared_terms=sorted(token_sets[i] & token_sets[j])[:8],
                        )
                    )

    pairs.sort(key=lambda p: p["similarity"], reverse=True)

    sys.stdout.write(
        envelope("deduplicate", {"pairs": pairs, "total": len(pairs), "threshold": threshold})
        + "\n"
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
        sys.stderr.write(
            "import reads guardrails from a JSON array, a full-fidelity JSON snapshot "
            "(guardrails + references + links), or a CSV file. Guardrails are upserted by ID "
            "or title; references and links are merged when provided. The index is rebuilt "
            "after import.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("import", "json")

    import csv as csv_mod
    from datetime import UTC, datetime
    from io import StringIO
    from pathlib import Path

    import orjson
    from pydantic import ValidationError
    from ulid import ULID

    from archguard.core.models import Guardrail, GuardrailImport, Link, Reference
    from archguard.core.store import (
        load_guardrails,
        load_links,
        load_references,
        load_taxonomy,
        rewrite_jsonl,
    )

    file_path = Path(file)
    if not file_path.exists():
        handle_error("import", "ERR_IO_FILE_NOT_FOUND", f"File not found: {file}")

    ext = file_path.suffix.lower()
    if ext not in (".json", ".csv"):
        handle_error(
            "import", "ERR_VALIDATION_FORMAT",
            f"Unsupported file extension: {ext}. Use .json or .csv",
        )

    data_dir = require_data_dir("import")
    guardrails = load_guardrails(data_dir)
    taxonomy = load_taxonomy(data_dir)
    by_id = {g.id: g for g in guardrails}
    by_title = {g.title: g for g in guardrails}

    raw_records: list[dict[str, Any]] = []
    raw_references: list[dict[str, Any]] = []
    raw_links: list[dict[str, Any]] = []
    errors: list[str] = []

    if ext == ".json":
        try:
            content = file_path.read_bytes()
            parsed: Any = orjson.loads(content)
            if isinstance(parsed, dict):
                parsed_dict = cast(dict[str, Any], parsed)
                result_payload = parsed_dict.get("result")
                if isinstance(result_payload, dict) and "guardrails" in result_payload:
                    parsed = cast(dict[str, Any], result_payload)
            if isinstance(parsed, list):
                raw_records = cast(list[dict[str, Any]], parsed)
            elif isinstance(parsed, dict):
                snapshot = cast(dict[str, Any], parsed)
                guardrails_value = snapshot.get("guardrails")
                references_value = snapshot.get("references", [])
                links_value = snapshot.get("links", [])
                if not isinstance(guardrails_value, list):
                    handle_error(
                        "import",
                        "ERR_VALIDATION_FORMAT",
                        "Snapshot JSON must contain a 'guardrails' array",
                    )
                if not isinstance(references_value, list) or not isinstance(links_value, list):
                    handle_error(
                        "import",
                        "ERR_VALIDATION_FORMAT",
                        "Snapshot JSON 'references' and 'links' fields must be arrays",
                    )
                raw_records = cast(list[dict[str, Any]], guardrails_value)
                raw_references = cast(list[dict[str, Any]], references_value)
                raw_links = cast(list[dict[str, Any]], links_value)
            else:
                handle_error(
                    "import",
                    "ERR_VALIDATION_FORMAT",
                    "JSON file must contain an array or snapshot object",
                )
        except orjson.JSONDecodeError as exc:
            handle_error("import", "ERR_VALIDATION_JSON", str(exc))
    else:
        text = file_path.read_text(encoding="utf-8")
        reader = csv_mod.DictReader(StringIO(text))
        for row_index, row in enumerate(reader):
            record: dict[str, Any] = dict(row)
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
            for optional_field in (
                "id",
                "public_id",
                "review_date",
                "superseded_by",
                "created_at",
                "updated_at",
            ):
                if optional_field in record and isinstance(record[optional_field], str):
                    value = record[optional_field].strip()
                    record[optional_field] = value or None
            if "metadata" in record and isinstance(record["metadata"], str):
                metadata_text = record["metadata"].strip()
                if not metadata_text:
                    record["metadata"] = {}
                else:
                    try:
                        metadata = orjson.loads(metadata_text)
                    except orjson.JSONDecodeError as exc:
                        errors.append(f"Record {row_index}: invalid metadata JSON: {exc}")
                        continue
                    if not isinstance(metadata, dict):
                        errors.append(
                            f"Record {row_index}: metadata must decode to a JSON object"
                        )
                        continue
                    record["metadata"] = metadata
            raw_records.append(record)

    new_count = 0
    updated_count = 0
    imported_reference_count = 0
    imported_link_count = 0
    now = datetime.now(UTC).isoformat()
    id_remap: dict[str, str] = {}

    for i, raw in enumerate(raw_records):
        try:
            imp = GuardrailImport.model_validate(raw)
        except ValidationError as exc:
            summary, _details = summarize_validation_error(exc)
            errors.append(f"Record {i}: {summary}")
            continue

        if taxonomy:
            bad_scopes = [s for s in imp.scope if s not in taxonomy]
            if bad_scopes:
                errors.append(f"Record {i}: invalid scope values: {bad_scopes}")
                continue

        # Upsert: match by ID first, then by title
        existing: Guardrail | None = None
        if imp.id and imp.id in by_id:
            existing = by_id[imp.id]
        elif imp.title in by_title:
            existing = by_title[imp.title]

        if existing is not None:
            merged = existing.model_dump()
            incoming_data = imp.model_dump(exclude_none=True)
            if (
                "public_id" in incoming_data
                and existing.public_id is not None
                and incoming_data["public_id"] != existing.public_id
            ):
                errors.append(
                    f"Record {i}: public_id '{incoming_data['public_id']}' does not match "
                    f"existing immutable value '{existing.public_id}'"
                )
                continue
            for field_name, value in imp.model_dump(exclude_none=True).items():
                if field_name not in ("id", "created_at"):
                    merged[field_name] = value
            if merged.get("public_id") is None:
                merged["public_id"] = imp.public_id or next_public_id(guardrails)
            merged["updated_at"] = imp.updated_at or now
            updated_obj = Guardrail.model_validate(merged)
            by_id[existing.id] = updated_obj
            by_title[updated_obj.title] = updated_obj
            for idx_val, g in enumerate(guardrails):
                if g.id == existing.id:
                    guardrails[idx_val] = updated_obj
                    break
            if imp.id:
                id_remap[imp.id] = existing.id
            updated_count += 1
        else:
            guardrail_id = imp.id or str(ULID())
            full = Guardrail(
                id=guardrail_id,
                public_id=imp.public_id or next_public_id(guardrails),
                title=imp.title,
                status=imp.status,
                severity=imp.severity,
                rationale=imp.rationale,
                guidance=imp.guidance,
                exceptions=imp.exceptions,
                consequences=imp.consequences,
                scope=imp.scope,
                applies_to=imp.applies_to,
                lifecycle_stage=imp.lifecycle_stage,
                owner=imp.owner,
                review_date=imp.review_date,
                superseded_by=imp.superseded_by,
                created_at=imp.created_at or now,
                updated_at=imp.updated_at or now,
                metadata=imp.metadata,
            )
            guardrails.append(full)
            by_id[full.id] = full
            by_title[full.title] = full
            if imp.id:
                id_remap[imp.id] = full.id
            new_count += 1

    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    if raw_references:
        references = load_references(data_dir)
        reference_map = {
            (
                ref.guardrail_id,
                ref.ref_type,
                ref.ref_id,
                ref.ref_title,
                ref.ref_url or "",
                ref.excerpt,
            ): ref
            for ref in references
        }
        valid_guardrail_ids = {g.id for g in guardrails}
        for i, raw_ref in enumerate(raw_references):
            try:
                ref = Reference.model_validate(raw_ref)
            except ValidationError as exc:
                summary, _details = summarize_validation_error(exc)
                errors.append(f"Reference {i}: {summary}")
                continue
            target_guardrail_id = id_remap.get(ref.guardrail_id, ref.guardrail_id)
            if target_guardrail_id not in valid_guardrail_ids:
                errors.append(
                    f"Reference {i}: guardrail_id '{ref.guardrail_id}' does not exist after import"
                )
                continue
            normalized_ref = Reference.model_validate(
                {**ref.model_dump(), "guardrail_id": target_guardrail_id}
            )
            key = (
                normalized_ref.guardrail_id,
                normalized_ref.ref_type,
                normalized_ref.ref_id,
                normalized_ref.ref_title,
                normalized_ref.ref_url or "",
                normalized_ref.excerpt,
            )
            is_new = key not in reference_map
            reference_map[key] = normalized_ref
            if is_new:
                imported_reference_count += 1
        rewrite_jsonl(data_dir / "references.jsonl", list(reference_map.values()))

    if raw_links:
        links = load_links(data_dir)
        link_map = {
            (link.from_id, link.to_id, link.rel_type, link.note): link
            for link in links
        }
        valid_guardrail_ids = {g.id for g in guardrails}
        for i, raw_link in enumerate(raw_links):
            try:
                link = Link.model_validate(raw_link)
            except ValidationError as exc:
                summary, _details = summarize_validation_error(exc)
                errors.append(f"Link {i}: {summary}")
                continue
            from_id = id_remap.get(link.from_id, link.from_id)
            to_id = id_remap.get(link.to_id, link.to_id)
            if from_id not in valid_guardrail_ids or to_id not in valid_guardrail_ids:
                errors.append(
                    f"Link {i}: endpoints '{link.from_id}' -> '{link.to_id}' "
                    "do not exist after import"
                )
                continue
            normalized_link = Link.model_validate(
                {**link.model_dump(), "from_id": from_id, "to_id": to_id}
            )
            key = (
                normalized_link.from_id,
                normalized_link.to_id,
                normalized_link.rel_type,
                normalized_link.note,
            )
            is_new = key not in link_map
            link_map[key] = normalized_link
            if is_new:
                imported_link_count += 1
        rewrite_jsonl(data_dir / "links.jsonl", list(link_map.values()))

    # Rebuild index
    from archguard.core.index import ensure_index

    emit_index_build_notice("import", data_dir)
    ensure_index(data_dir)

    sys.stdout.write(
        envelope(
            "import",
            {
                "imported": new_count,
                "updated": updated_count,
                "references_imported": imported_reference_count,
                "links_imported": imported_link_count,
                "errors": errors,
            },
        )
        + "\n"
    )
