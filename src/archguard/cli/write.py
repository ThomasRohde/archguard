"""Write commands: add, update, ref-add, link, deprecate, supersede."""

from __future__ import annotations

import sys
from typing import Annotated, Any

import typer

from archguard.cli import (
    app,
    emit_index_build_notice,
    ensure_supported_format,
    handle_error,
    require_data_dir,
    summarize_validation_error,
)
from archguard.output.json import envelope


def _has_reference_evidence(references: list[Any]) -> bool:
    """Return True if any reference includes a non-empty excerpt."""
    return any(bool(getattr(ref, "excerpt", "").strip()) for ref in references)


def _enforce_active_requirements(
    command: str,
    *,
    status: str,
    owner: str,
    references: list[Any],
) -> None:
    """Require evidence-backed references and accountable ownership for active guardrails."""
    if status != "active":
        return

    from archguard.core.validator import owner_is_placeholder

    if len(references) == 0:
        handle_error(
            command,
            "ERR_VALIDATION",
            (
                "Active guardrails require at least one reference."
                " Add references first, or create the guardrail as draft and promote it later."
            ),
            details={"status": status, "references": 0},
        )

    if not _has_reference_evidence(references):
        handle_error(
            command,
            "ERR_VALIDATION",
            (
                "Active guardrails require at least one reference excerpt "
                "showing the source evidence."
                " Add an excerpt, or keep the guardrail as draft until evidence is captured."
            ),
            details={"status": status, "references": len(references), "has_excerpt": False},
        )

    if owner_is_placeholder(owner):
        handle_error(
            command,
            "ERR_VALIDATION",
            (
                "Active guardrails require a non-placeholder owner."
                " Use a neutral placeholder such as 'unassigned' only for draft records."
            ),
            details={"status": status, "owner": owner},
        )


def _add_schema_contract(schema_data: dict[str, Any]) -> dict[str, Any]:
    """Augment the raw Pydantic schema with authoring guidance for agents."""
    return {
        "schema": schema_data,
        "provenance_contract": {
            "principle": (
                "Never present inferred or defaulted values as if they were stated by the source."
            ),
            "draft_when": [
                (
                    "Owner is unknown and must be defaulted to a neutral "
                    "placeholder such as 'unassigned'."
                ),
                "Scope or lifecycle_stage must be inferred.",
                "No source excerpt is available for the rule.",
            ],
            "metadata_hint": (
                "If fields are inferred or defaulted, record that fact in metadata, for example "
                "metadata.field_derivation.owner='defaulted'."
            ),
        },
        "minimum_evidence": {
            "active_guardrail_requires": [
                "At least one authoritative reference.",
                "At least one non-empty reference excerpt showing the evidence for the rule.",
                "A non-placeholder owner."
            ],
            "draft_guardrail_allows": [
                "Placeholder owner such as 'unassigned'.",
                "Missing review_date.",
                "Inferred applies_to and lifecycle_stage values."
            ],
        },
        "defaulting_policy": {
            "owner": (
                "Do not infer a precise owner from generic source material. Use 'unassigned' and "
                "keep status=draft when the accountable owner is not stated."
            ),
            "review_date": (
                "Do not invent review_date from source material. Set it only "
                "from repository policy "
                "or human input."
            ),
        },
    }


@app.command()
def add(
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
    schema: Annotated[bool, typer.Option("--schema", help="Print input JSON schema")] = False,
) -> None:
    """Add a new guardrail from JSON on stdin. Optionally includes inline references."""
    if explain:
        sys.stderr.write(
            "add reads a guardrail JSON object from stdin, validates it, generates a ULID, "
            "appends it to guardrails.jsonl, rebuilds the index, and returns the created record.\n"
            "\n"
            "WHEN TO USE: You have identified an atomic architectural rule from an authoritative\n"
            "source and confirmed (via 'archguard search') that no duplicate exists.\n"
            "\n"
            "WHEN NOT TO USE:\n"
            "  - Source is background context, not a rule -> use ref-add instead.\n"
            "  - An existing guardrail covers this -> use update or link instead.\n"
            "  - Source is vague with no clear normative action -> do not create.\n"
            "\n"
            "COMMON MISTAKES:\n"
            "  - Compound rules: split into one guardrail per atomic rule.\n"
            "  - Severity too high: must requires authoritative mandate, not model confidence.\n"
            "  - Vague guidance: 'follow best practices' is not actionable.\n"
            "  - Invented owner: do not guess a precise team from generic source material.\n"
            "  - Invented review_date: only set it from policy or human input.\n"
            "  - Missing evidence: active guardrails must cite their source and include "
            "an excerpt.\n"
            "  - Overconfident metadata: inferred scope/lifecycle values should usually "
            "stay draft.\n"
            "\n"
            "DRAFT VS ACTIVE:\n"
            "  - Use status=draft when owner, scope, lifecycle, or review timing is inferred.\n"
            "  - A neutral placeholder such as 'unassigned' is acceptable for draft records.\n"
            "  - status=active is reserved for rules with authoritative evidence and "
            "accountable ownership.\n"
            "\n"
            "Call 'archguard add --schema' to see the exact input JSON schema.\n"
        )
        raise SystemExit(0)
    if schema:
        from archguard.core.models import GuardrailCreate

        schema_data = GuardrailCreate.model_json_schema()
        sys.stdout.write(envelope("add", _add_schema_contract(schema_data)) + "\n")
        raise SystemExit(0)

    ensure_supported_format("add", "json")

    import orjson
    from pydantic import ValidationError
    from ulid import ULID

    from archguard.core.index import ensure_index
    from archguard.core.models import Guardrail, GuardrailCreate, Reference
    from archguard.core.store import append_jsonl, load_guardrails, load_taxonomy

    data_dir = require_data_dir("add")

    # Read JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        handle_error("add", "ERR_VALIDATION", "No JSON input provided on stdin")

    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as e:
        handle_error("add", "ERR_VALIDATION_JSON", f"Invalid JSON: {e}")

    try:
        create = GuardrailCreate.model_validate(payload)
    except ValidationError as e:
        message, details = summarize_validation_error(e)
        handle_error("add", "ERR_VALIDATION", message, details)
        return  # unreachable, keeps type checker happy

    # Validate scope against taxonomy
    taxonomy = load_taxonomy(data_dir)
    if taxonomy:
        for s in create.scope:
            if s not in taxonomy:
                handle_error(
                    "add",
                    "ERR_VALIDATION",
                    f"Scope '{s}' not in taxonomy. Allowed: {taxonomy}",
                )

    # Check for duplicate title
    existing = load_guardrails(data_dir)
    for g in existing:
        if g.title == create.title:
            handle_error(
                "add", "ERR_CONFLICT_EXISTS",
                f"Guardrail with title '{create.title}' already exists",
            )

    _enforce_active_requirements(
        "add",
        status=create.status,
        owner=create.owner,
        references=create.references,
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
    refs_for_checks: list[Reference] = []
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
            refs_for_checks.append(ref)

    # Rebuild index
    emit_index_build_notice("add", data_dir)
    ensure_index(data_dir)

    # Check authoring quality (RFC 2119 consistency + semantic warnings)
    from archguard.core.validator import check_authoring_quality, check_severity_consistency

    all_warnings = check_severity_consistency(guardrail)

    # For must+active guardrails, pass inline refs for reference-presence check
    inline_refs = refs_for_checks if refs_for_checks else None
    all_warnings.extend(
        check_authoring_quality(guardrail, references=inline_refs),
    )

    sys.stdout.write(
        envelope(
            "add",
            {"guardrail": guardrail.model_dump(), "references": refs_created},
            warnings=all_warnings or None,
        )
        + "\n"
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
        sys.stderr.write(
            "update reads a partial JSON patch from stdin, merges it with the existing guardrail, "
            "rewrites the JSONL line, and rebuilds the index. Only provided fields are changed.\n"
            "\n"
            "WHEN TO USE: Refining an existing guardrail — correcting wording,\n"
            "adjusting severity, narrowing scope, or promoting draft to active.\n"
            "\n"
            "WHEN NOT TO USE:\n"
            "  - Rule is fundamentally different -> create new guardrail and link/supersede.\n"
            "  - You want to set status=superseded -> use the 'supersede' command instead.\n"
            "\n"
            "Only provided fields are changed (patch semantics). Omitted fields are untouched.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("update", "json")

    import orjson
    from pydantic import ValidationError

    from archguard.core.models import GuardrailPatch
    from archguard.core.store import load_guardrails, load_taxonomy, rewrite_jsonl

    data_dir = require_data_dir("update")

    # Read patch JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        handle_error("update", "ERR_VALIDATION", "No JSON input provided on stdin")

    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as e:
        handle_error("update", "ERR_VALIDATION_JSON", f"Invalid JSON: {e}")

    try:
        patch = GuardrailPatch.model_validate(payload)
    except ValidationError as e:
        message, details = summarize_validation_error(e)
        handle_error("update", "ERR_VALIDATION", message, details)
        return

    # Disallow status changes to superseded via update — use supersede command
    if patch.status == "superseded":
        handle_error(
            "update", "ERR_CONFLICT_TRANSITION",
            "Use the 'supersede' command to supersede a guardrail",
        )

    # Validate scope against taxonomy if provided
    if patch.scope is not None:
        taxonomy = load_taxonomy(data_dir)
        if taxonomy:
            for s in patch.scope:
                if s not in taxonomy:
                    handle_error(
                        "update", "ERR_VALIDATION",
                        f"Scope '{s}' not in taxonomy. Allowed: {taxonomy}",
                    )

    # Find guardrail
    guardrails = load_guardrails(data_dir)
    idx = next((i for i, g in enumerate(guardrails) if g.id == guardrail_id), None)

    if idx is None:
        handle_error("update", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found")
        return

    # Merge patch fields
    from datetime import UTC, datetime

    from archguard.core.models import Guardrail
    from archguard.core.store import load_references

    patch_data = patch.model_dump(exclude_none=True)
    updated_data = guardrails[idx].model_dump()
    updated_data.update(patch_data)
    updated_data["updated_at"] = datetime.now(UTC).isoformat()

    existing_refs = [r for r in load_references(data_dir) if r.guardrail_id == guardrail_id]
    _enforce_active_requirements(
        "update",
        status=updated_data["status"],
        owner=updated_data["owner"],
        references=existing_refs,
    )

    guardrails[idx] = Guardrail.model_validate(updated_data)
    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    # Rebuild index
    from archguard.core.index import ensure_index

    emit_index_build_notice("update", data_dir)
    ensure_index(data_dir)

    # Check authoring quality (RFC 2119 consistency + semantic warnings)
    from archguard.core.validator import check_authoring_quality, check_severity_consistency

    all_warnings = check_severity_consistency(guardrails[idx])

    # Load references for must+active reference-presence check
    refs = existing_refs
    all_warnings.extend(
        check_authoring_quality(guardrails[idx], references=refs),
    )

    sys.stdout.write(
        envelope(
            "update",
            {"guardrail": guardrails[idx].model_dump()},
            warnings=all_warnings or None,
        )
        + "\n"
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
        sys.stderr.write(
            "ref-add reads a reference JSON from stdin, validates it, appends to references.jsonl, "
            "and rebuilds the index.\n"
            "\n"
            "WHEN TO USE: Attaching an authoritative source (ADR, policy, standard, regulation,\n"
            "pattern, document) to an existing guardrail. Active guardrails should have at least\n"
            "one reference.\n"
            "\n"
            "WHEN NOT TO USE:\n"
            "  - The source material is a new rule -> use 'add' to create a guardrail first.\n"
            "  - You want to link two guardrails -> use 'link' instead.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("ref-add", "json")

    import orjson
    from pydantic import ValidationError

    from archguard.core.models import Reference, ReferenceCreate
    from archguard.core.store import append_jsonl, load_guardrails

    data_dir = require_data_dir("ref-add")

    # Read reference JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        handle_error("ref-add", "ERR_VALIDATION", "No JSON input provided on stdin")

    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as e:
        handle_error("ref-add", "ERR_VALIDATION_JSON", f"Invalid JSON: {e}")

    try:
        ref_create = ReferenceCreate.model_validate(payload)
    except ValidationError as e:
        message, details = summarize_validation_error(e)
        handle_error("ref-add", "ERR_VALIDATION", message, details)
        return

    # Verify guardrail exists
    guardrails = load_guardrails(data_dir)
    if not any(g.id == guardrail_id for g in guardrails):
        handle_error("ref-add", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found")

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

    # Rebuild index
    from archguard.core.index import ensure_index

    emit_index_build_notice("ref-add", data_dir)
    ensure_index(data_dir)

    sys.stdout.write(
        envelope("ref-add", {"reference": ref.model_dump()}) + "\n"
    )


@app.command()
def link(
    from_id: Annotated[str, typer.Argument(help="ULID of the source guardrail")],
    to_id: Annotated[str, typer.Argument(help="ULID of the target guardrail")],
    rel: Annotated[
        str,
        typer.Option(
            "--rel",
            help="Relationship type: supports, conflicts, refines, implements, requires",
        ),
    ],
    note: Annotated[str, typer.Option("--note", help="Optional annotation")] = "",
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Create a typed relationship between two guardrails."""
    if explain:
        sys.stderr.write(
            "link creates a directional relationship between two guardrails "
            "and appends it to links.jsonl.\n"
            "\n"
            "RELATIONSHIP TYPES:\n"
            "  supports    — A reinforces B (complementary rules).\n"
            "  conflicts   — A and B are in tension (document the trade-off).\n"
            "  refines     — A is a more specific version of B.\n"
            "  implements  — A is a concrete implementation of B.\n"
            "  requires    — A depends on B being in place.\n"
            "\n"
            "WHEN TO USE: Two guardrails are related and the relationship should be\n"
            "explicitly captured for traceability.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("link", "json")

    from archguard.core.models import Link as LinkModel
    from archguard.core.store import append_jsonl, load_guardrails

    data_dir = require_data_dir("link")

    # Validate rel type
    valid_rels = {"supports", "conflicts", "refines", "implements", "requires"}
    if rel not in valid_rels:
        handle_error(
            "link", "ERR_VALIDATION",
            f"Invalid rel type '{rel}'. Must be one of: {sorted(valid_rels)}",
        )

    # Verify both guardrails exist
    guardrails = load_guardrails(data_dir)
    ids = {g.id for g in guardrails}
    if from_id not in ids:
        handle_error("link", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{from_id}' not found")
    if to_id not in ids:
        handle_error("link", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{to_id}' not found")

    link_record = LinkModel(
        from_id=from_id,
        to_id=to_id,
        rel_type=rel,  # type: ignore[arg-type]  # validated above
        note=note,
    )
    append_jsonl(data_dir / "links.jsonl", link_record)

    # Rebuild index
    from archguard.core.index import ensure_index

    emit_index_build_notice("link", data_dir)
    ensure_index(data_dir)

    sys.stdout.write(
        envelope("link", {"link": link_record.model_dump()}) + "\n"
    )


@app.command()
def delete(
    guardrail_id: Annotated[str, typer.Argument(help="ULID of the guardrail to delete")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Confirm deletion")] = False,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Permanently delete a guardrail and its associated references and links."""
    if explain:
        sys.stderr.write(
            "delete removes a guardrail from guardrails.jsonl and cleans up "
            "associated references and links. Requires --confirm flag "
            "(auto-confirmed when LLM=true). Rebuilds the index afterward.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("delete", "json")

    from archguard.output.json import is_llm_mode

    if not confirm and not is_llm_mode():
        handle_error(
            "delete", "ERR_VALIDATION",
            "Deletion requires --confirm flag (auto-confirmed when LLM=true)",
        )

    from archguard.core.index import ensure_index
    from archguard.core.store import (
        load_guardrails,
        load_links,
        load_references,
        rewrite_jsonl,
    )

    data_dir = require_data_dir("delete")
    guardrails = load_guardrails(data_dir)

    target = next((g for g in guardrails if g.id == guardrail_id), None)
    if target is None:
        handle_error("delete", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found")
        return

    # Remove guardrail
    guardrails = [g for g in guardrails if g.id != guardrail_id]
    rewrite_jsonl(data_dir / "guardrails.jsonl", guardrails)

    # Clean up references
    refs = load_references(data_dir)
    refs_removed = sum(1 for r in refs if r.guardrail_id == guardrail_id)
    refs = [r for r in refs if r.guardrail_id != guardrail_id]
    rewrite_jsonl(data_dir / "references.jsonl", refs)

    # Clean up links
    links = load_links(data_dir)
    links_removed = sum(
        1 for lnk in links if lnk.from_id == guardrail_id or lnk.to_id == guardrail_id
    )
    links = [
        lnk for lnk in links
        if lnk.from_id != guardrail_id and lnk.to_id != guardrail_id
    ]
    rewrite_jsonl(data_dir / "links.jsonl", links)

    # Rebuild index
    emit_index_build_notice("delete", data_dir)
    ensure_index(data_dir)

    sys.stdout.write(
        envelope("delete", {
            "deleted": target.model_dump(),
            "references_removed": refs_removed,
            "links_removed": links_removed,
        }) + "\n"
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
        sys.stderr.write(
            "deprecate sets the guardrail's status to 'deprecated' "
            "and records the reason in metadata.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("deprecate", "json")

    from archguard.core.store import load_guardrails, rewrite_jsonl

    data_dir = require_data_dir("deprecate")

    guardrails = load_guardrails(data_dir)
    idx = next((i for i, g in enumerate(guardrails) if g.id == guardrail_id), None)

    if idx is None:
        handle_error(
            "deprecate", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found",
        )
        return

    # Validate transition: only draft/active can be deprecated
    if guardrails[idx].status not in ("draft", "active"):
        handle_error(
            "deprecate", "ERR_CONFLICT_TRANSITION",
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

    # Rebuild index
    from archguard.core.index import ensure_index

    emit_index_build_notice("deprecate", data_dir)
    ensure_index(data_dir)

    sys.stdout.write(
        envelope("deprecate", {"guardrail": guardrails[idx].model_dump()}) + "\n"
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
        sys.stderr.write(
            "supersede sets superseded_by on the old guardrail, "
            "changes its status to 'superseded', and creates an "
            "'implements' link from the new guardrail to the old one.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("supersede", "json")

    from archguard.core.models import Guardrail
    from archguard.core.models import Link as LinkModel
    from archguard.core.store import append_jsonl, load_guardrails, rewrite_jsonl

    data_dir = require_data_dir("supersede")

    guardrails = load_guardrails(data_dir)
    ids = {g.id for g in guardrails}

    if guardrail_id not in ids:
        handle_error(
            "supersede", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found",
        )
    if by not in ids:
        handle_error(
            "supersede", "ERR_RESOURCE_NOT_FOUND",
            f"Replacement guardrail '{by}' not found",
        )

    idx = next((i for i, g in enumerate(guardrails) if g.id == guardrail_id), None)

    if idx is None:
        handle_error(
            "supersede", "ERR_RESOURCE_NOT_FOUND", f"Guardrail '{guardrail_id}' not found",
        )
        return

    # Validate transition
    if guardrails[idx].status not in ("draft", "active"):
        handle_error(
            "supersede", "ERR_CONFLICT_TRANSITION",
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

    # Rebuild index
    from archguard.core.index import ensure_index

    emit_index_build_notice("supersede", data_dir)
    ensure_index(data_dir)

    sys.stdout.write(
        envelope("supersede", {
            "guardrail": guardrails[idx].model_dump(),
            "link": link_record.model_dump(),
        }) + "\n"
    )
