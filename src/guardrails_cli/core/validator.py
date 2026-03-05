"""Integrity checks for JSONL data (used by `guardrails validate`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from guardrails_cli.core.store import load_guardrails, load_links, load_references, load_taxonomy


@dataclass
class ValidationResult:
    """Collects all validation issues found."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def validate_corpus(data_dir: Path) -> ValidationResult:
    """Run all integrity checks on the guardrails corpus.

    Checks performed:
    1. All JSONL files parse correctly via Pydantic
    2. All reference guardrail_ids point to existing guardrails
    3. All link from_id/to_id point to existing guardrails
    4. All scope values match the taxonomy (if taxonomy is non-empty)
    5. No duplicate guardrail IDs
    """
    result = ValidationResult()
    taxonomy = load_taxonomy(data_dir)

    # Load guardrails
    try:
        guardrails = load_guardrails(data_dir)
    except Exception as e:
        result.errors.append(f"Failed to parse guardrails.jsonl: {e}")
        return result

    # Check for duplicate IDs
    ids = [g.id for g in guardrails]
    id_set = set(ids)
    if len(ids) != len(id_set):
        seen: set[str] = set()
        for gid in ids:
            if gid in seen:
                result.errors.append(f"Duplicate guardrail ID: {gid}")
            seen.add(gid)

    # Validate scope against taxonomy
    if taxonomy:
        for g in guardrails:
            for s in g.scope:
                if s not in taxonomy:
                    result.errors.append(
                        f"Guardrail {g.id}: scope '{s}' not in taxonomy. Allowed: {taxonomy}"
                    )

    # Load and check references
    try:
        references = load_references(data_dir)
        for ref in references:
            if ref.guardrail_id not in id_set:
                result.errors.append(
                    f"Orphan reference: ref_id={ref.ref_id} points to "
                    f"non-existent guardrail {ref.guardrail_id}"
                )
    except Exception as e:
        result.errors.append(f"Failed to parse references.jsonl: {e}")

    # Load and check links
    try:
        links = load_links(data_dir)
        for link in links:
            if link.from_id not in id_set:
                result.errors.append(f"Broken link: from_id {link.from_id} not found")
            if link.to_id not in id_set:
                result.errors.append(f"Broken link: to_id {link.to_id} not found")
    except Exception as e:
        result.errors.append(f"Failed to parse links.jsonl: {e}")

    return result
