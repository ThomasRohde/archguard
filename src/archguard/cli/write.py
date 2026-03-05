"""Write commands: add, update, ref-add, link, deprecate, supersede."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from archguard.cli import app, handle_error, state


@app.command()
def add(
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
    schema: Annotated[bool, typer.Option("--schema", help="Print input JSON schema")] = False,
) -> None:
    """Add a new guardrail from JSON on stdin. Optionally includes inline references."""
    if explain:
        sys.stdout.write(
            "add reads a guardrail JSON object from stdin, validates it, generates a ULID, "
            "appends it to guardrails.jsonl, rebuilds the index, and returns the created record.\n"
        )
        raise SystemExit(0)
    if schema:
        from archguard.core.models import GuardrailCreate

        sys.stdout.write(GuardrailCreate.model_json_schema_str() + "\n")
        raise SystemExit(0)

    import orjson
    from pydantic import ValidationError
    from ulid import ULID

    from archguard.core.index import ensure_index
    from archguard.core.models import Guardrail, GuardrailCreate, Reference
    from archguard.core.store import append_jsonl, load_guardrails, load_taxonomy
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)

    # Read JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        handle_error(20, "validation_error", "No JSON input provided on stdin")

    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as e:
        handle_error(20, "validation_error", f"Invalid JSON: {e}")

    try:
        create = GuardrailCreate.model_validate(payload)
    except ValidationError as e:
        handle_error(20, "validation_error", f"Validation failed: {e}")
        return  # unreachable, keeps type checker happy

    # Validate scope against taxonomy
    taxonomy = load_taxonomy(data_dir)
    if taxonomy:
        for s in create.scope:
            if s not in taxonomy:
                handle_error(
                    20,
                    "validation_error",
                    f"Scope '{s}' not in taxonomy. Allowed: {taxonomy}",
                )

    # Check for duplicate title
    existing = load_guardrails(data_dir)
    for g in existing:
        if g.title == create.title:
            handle_error(
                11, "already_exists", f"Guardrail with title '{create.title}' already exists"
            )

    # Generate ID and timestamps
    from datetime import UTC, datetime

    guardrail_id = str(ULID())
    now = datetime.now(UTC).isoformat()

    guardrail = Guardrail(
        id=guardrail_id,
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
        metadata=create.metadata,
        created_at=now,
        updated_at=now,
    )

    append_jsonl(data_dir / "guardrails.jsonl", guardrail)

    # Handle inline references
    refs_created: list[dict[str, Any]] = []
    if create.references:
        for ref_create in create.references:
            ref = Reference(
                guardrail_id=guardrail_id,
                ref_type=ref_create.ref_type,
                ref_id=ref_create.ref_id,
                ref_title=ref_create.ref_title,
                ref_url=ref_create.ref_url,
                excerpt=ref_create.excerpt,
                added_at=now,
            )
            append_jsonl(data_dir / "references.jsonl", ref)
            refs_created.append(ref.model_dump())

    # Rebuild index
    ensure_index(data_dir)

    sys.stdout.write(
        success_response({"guardrail": guardrail.model_dump(), "references": refs_created}) + "\n"
    )


@app.command()
def update(
    guardrail_id: Annotated[str, typer.Argument(help="ULID of the guardrail to update")],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Partially update a guardrail with patch semantics. Reads patch JSON from stdin."""
    if explain:
        sys.stdout.write(
            "update reads a partial JSON patch from stdin, merges it with the existing guardrail, "
            "rewrites the JSONL line, and rebuilds the index. Only provided fields are changed.\n"
        )
        raise SystemExit(0)

    import orjson
    from pydantic import ValidationError

    from archguard.core.models import GuardrailPatch
    from archguard.core.store import load_guardrails, load_taxonomy, rewrite_jsonl
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)

    # Read patch JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        handle_error(20, "validation_error", "No JSON input provided on stdin")

    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as e:
        handle_error(20, "validation_error", f"Invalid JSON: {e}")

    try:
        patch = GuardrailPatch.model_validate(payload)
    except ValidationError as e:
        handle_error(20, "validation_error", f"Validation failed: {e}")
        return

    # Disallow status changes to superseded via update — use supersede command
    if patch.status == "superseded":
        handle_error(
            12, "invalid_transition",
            "Use the 'supersede' command to supersede a guardrail",
        )

    # Validate scope against taxonomy if provided
    if patch.scope is not None:
        taxonomy = load_taxonomy(data_dir)
        if taxonomy:
            for s in patch.scope:
                if s not in taxonomy:
                    handle_error(
                        20, "validation_error",
                        f"Scope '{s}' not in taxonomy. Allowed: {taxonomy}",
                    )

    # Find guardrail
    guardrails = load_guardrails(data_dir)
    idx = next((i for i, g in enumerate(guardrails) if g.id == guardrail_id), None)

    if idx is None:
        handle_error(10, "not_found", f"Guardrail '{guardrail_id}' not found")
        return

    # Merge patch fields
    from datetime import UTC, datetime

    from archguard.core.models import Guardrail

    patch_data = patch.model_dump(exclude_none=True)
    updated_data = guardrails[idx].model_dump()
    updated_data.update(patch_data)
    updated_data["updated_at"] = datetime.now(UTC).isoformat()

    guardrails[idx] = Guardrail.model_validate(updated_data)
    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    sys.stdout.write(
        success_response({"guardrail": guardrails[idx].model_dump()}) + "\n"
    )


@app.command(name="ref-add")
def ref_add(
    guardrail_id: Annotated[
        str, typer.Argument(help="ULID of the guardrail to add a reference to")
    ],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Add a reference/citation to an existing guardrail. Reads reference JSON from stdin."""
    if explain:
        sys.stdout.write(
            "ref-add reads a reference JSON from stdin, validates it, appends to references.jsonl, "
            "and rebuilds the index.\n"
        )
        raise SystemExit(0)

    import orjson
    from pydantic import ValidationError

    from archguard.core.models import Reference, ReferenceCreate
    from archguard.core.store import append_jsonl, load_guardrails
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)

    # Read reference JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        handle_error(20, "validation_error", "No JSON input provided on stdin")

    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as e:
        handle_error(20, "validation_error", f"Invalid JSON: {e}")

    try:
        ref_create = ReferenceCreate.model_validate(payload)
    except ValidationError as e:
        handle_error(20, "validation_error", f"Validation failed: {e}")
        return

    # Verify guardrail exists
    guardrails = load_guardrails(data_dir)
    if not any(g.id == guardrail_id for g in guardrails):
        handle_error(10, "not_found", f"Guardrail '{guardrail_id}' not found")

    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    ref = Reference(
        guardrail_id=guardrail_id,
        ref_type=ref_create.ref_type,
        ref_id=ref_create.ref_id,
        ref_title=ref_create.ref_title,
        ref_url=ref_create.ref_url,
        excerpt=ref_create.excerpt,
        added_at=now,
    )
    append_jsonl(data_dir / "references.jsonl", ref)

    sys.stdout.write(
        success_response({"reference": ref.model_dump()}) + "\n"
    )


@app.command()
def link(
    from_id: Annotated[str, typer.Argument(help="ULID of the source guardrail")],
    to_id: Annotated[str, typer.Argument(help="ULID of the target guardrail")],
    rel: Annotated[
        str,
        typer.Option("--rel", help="Relationship type: supports, conflicts, refines, implements"),
    ],
    note: Annotated[str, typer.Option("--note", help="Optional annotation")] = "",
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Create a typed relationship between two guardrails."""
    if explain:
        sys.stdout.write(
            "link creates a directional relationship between two guardrails "
            "and appends it to links.jsonl.\n"
        )
        raise SystemExit(0)

    from archguard.core.models import Link as LinkModel
    from archguard.core.store import append_jsonl, load_guardrails
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)

    # Validate rel type
    valid_rels = {"supports", "conflicts", "refines", "implements"}
    if rel not in valid_rels:
        handle_error(
            20, "validation_error",
            f"Invalid rel type '{rel}'. Must be one of: {sorted(valid_rels)}",
        )

    # Verify both guardrails exist
    guardrails = load_guardrails(data_dir)
    ids = {g.id for g in guardrails}
    if from_id not in ids:
        handle_error(10, "not_found", f"Guardrail '{from_id}' not found")
    if to_id not in ids:
        handle_error(10, "not_found", f"Guardrail '{to_id}' not found")

    link_record = LinkModel(
        from_id=from_id,
        to_id=to_id,
        rel_type=rel,  # type: ignore[arg-type]  # validated above
        note=note,
    )
    append_jsonl(data_dir / "links.jsonl", link_record)

    sys.stdout.write(
        success_response({"link": link_record.model_dump()}) + "\n"
    )


@app.command()
def deprecate(
    guardrail_id: Annotated[str, typer.Argument(help="ULID of the guardrail to deprecate")],
    reason: Annotated[str, typer.Option("--reason", help="Reason for deprecation")],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Mark a guardrail as deprecated."""
    if explain:
        sys.stdout.write(
            "deprecate sets the guardrail's status to 'deprecated' "
            "and records the reason in metadata.\n"
        )
        raise SystemExit(0)

    from archguard.core.store import load_guardrails, rewrite_jsonl
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)

    guardrails = load_guardrails(data_dir)
    idx = next((i for i, g in enumerate(guardrails) if g.id == guardrail_id), None)

    if idx is None:
        handle_error(10, "not_found", f"Guardrail '{guardrail_id}' not found")
        return

    # Validate transition: only draft/active can be deprecated
    if guardrails[idx].status not in ("draft", "active"):
        handle_error(
            12, "invalid_transition",
            f"Cannot deprecate guardrail with status '{guardrails[idx].status}'."
            " Must be 'draft' or 'active'.",
        )

    from datetime import UTC, datetime

    from archguard.core.models import Guardrail

    updated_data = guardrails[idx].model_dump()
    updated_data["status"] = "deprecated"
    updated_data["metadata"]["deprecation_reason"] = reason
    updated_data["updated_at"] = datetime.now(UTC).isoformat()

    guardrails[idx] = Guardrail.model_validate(updated_data)
    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    sys.stdout.write(
        success_response({"guardrail": guardrails[idx].model_dump()}) + "\n"
    )


@app.command()
def supersede(
    guardrail_id: Annotated[str, typer.Argument(help="ULID of the guardrail being superseded")],
    by: Annotated[str, typer.Option("--by", help="ULID of the replacement guardrail")],
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Mark a guardrail as superseded by another, creating a link."""
    if explain:
        sys.stdout.write(
            "supersede sets superseded_by on the old guardrail, "
            "changes its status to 'superseded', and creates an "
            "'implements' link from the new guardrail to the old one.\n"
        )
        raise SystemExit(0)

    from archguard.core.models import Guardrail
    from archguard.core.models import Link as LinkModel
    from archguard.core.store import append_jsonl, load_guardrails, rewrite_jsonl
    from archguard.output.json import success_response

    data_dir = Path(state.data_dir)

    guardrails = load_guardrails(data_dir)
    ids = {g.id for g in guardrails}

    if guardrail_id not in ids:
        handle_error(10, "not_found", f"Guardrail '{guardrail_id}' not found")
    if by not in ids:
        handle_error(10, "not_found", f"Replacement guardrail '{by}' not found")

    idx = next((i for i, g in enumerate(guardrails) if g.id == guardrail_id), None)

    if idx is None:
        handle_error(10, "not_found", f"Guardrail '{guardrail_id}' not found")
        return

    # Validate transition
    if guardrails[idx].status not in ("draft", "active"):
        handle_error(
            12, "invalid_transition",
            f"Cannot supersede guardrail with status '{guardrails[idx].status}'."
            " Must be 'draft' or 'active'.",
        )

    from datetime import UTC, datetime

    updated_data = guardrails[idx].model_dump()
    updated_data["status"] = "superseded"
    updated_data["superseded_by"] = by
    updated_data["updated_at"] = datetime.now(UTC).isoformat()

    guardrails[idx] = Guardrail.model_validate(updated_data)
    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    # Create implements link: new -> old
    link_record = LinkModel(
        from_id=by, to_id=guardrail_id, rel_type="implements", note="",
    )
    append_jsonl(data_dir / "links.jsonl", link_record)

    sys.stdout.write(
        success_response({
            "guardrail": guardrails[idx].model_dump(),
            "link": link_record.model_dump(),
        }) + "\n"
    )
