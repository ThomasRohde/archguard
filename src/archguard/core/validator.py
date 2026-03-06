"""Integrity checks for JSONL data (used by `guardrails validate`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from archguard.core.models import Guardrail
from archguard.core.store import load_guardrails, load_links, load_references, load_taxonomy

# ---------------------------------------------------------------------------
# RFC 2119 severity-consistency check
# ---------------------------------------------------------------------------

# Word-boundary patterns for RFC 2119 keywords (case-insensitive).
# Groups: positive obligation ("must", "shall", "required"),
#         recommendation ("should", "recommended"),
#         permission ("may", "optional").
_RFC2119_POSITIVE = re.compile(
    r"\b(must(?:\s+not)?|shall(?:\s+not)?|required|not\s+required)\b", re.IGNORECASE,
)
_RFC2119_RECOMMEND = re.compile(
    r"\b(should(?:\s+not)?|recommended|not\s+recommended)\b", re.IGNORECASE,
)
_RFC2119_OPTIONAL = re.compile(
    r"\b(may(?:\s+not)?|optional)\b", re.IGNORECASE,
)

# Which keyword families conflict with each declared severity level.
# A "must" guardrail should not use "should"/"may" language (weakens the mandate).
# A "should" guardrail should not use "must" (overstates) or "may" (understates).
# A "may" guardrail should not use "must"/"should" (overstates).
_CONFLICTING: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "must": [
        (_RFC2119_RECOMMEND, "should/recommended"),
        (_RFC2119_OPTIONAL, "may/optional"),
    ],
    "should": [
        (_RFC2119_POSITIVE, "must/shall/required"),
        (_RFC2119_OPTIONAL, "may/optional"),
    ],
    "may": [
        (_RFC2119_POSITIVE, "must/shall/required"),
        (_RFC2119_RECOMMEND, "should/recommended"),
    ],
}

_TEXT_FIELDS = ("guidance", "rationale", "exceptions", "consequences")


def check_severity_consistency(guardrail: Guardrail) -> list[str]:
    """Return warnings if the guardrail text uses RFC 2119 keywords that conflict
    with its declared severity level."""
    warnings: list[str] = []
    conflicts = _CONFLICTING.get(guardrail.severity, [])
    for field_name in _TEXT_FIELDS:
        text: str = getattr(guardrail, field_name, "")
        if not text:
            continue
        for pattern, label in conflicts:
            match = pattern.search(text)
            if match:
                warnings.append(
                    f"Guardrail {guardrail.id[:8]} ({guardrail.severity}): "
                    f"{field_name} contains '{match.group()}' "
                    f"(conflicting {label} language)"
                )
    return warnings


def check_authoring_quality(
    guardrail: Guardrail,
    references: list | None = None,
) -> list[str]:
    """Return warnings for common authoring quality issues.

    These are non-fatal: the guardrail is structurally valid but may be
    semantically weak. Designed to help weaker models self-correct.
    """
    warnings: list[str] = []
    gid = guardrail.id[:8]

    # Vague title: multi-sentence, or contains weak verbs
    if ". " in guardrail.title or "? " in guardrail.title:
        warnings.append(
            f"Guardrail {gid}: title contains multiple sentences. "
            f"Prefer one short imperative rule."
        )
    _VAGUE_TITLE_RE = re.compile(
        r"\b(optimize|improve|support|ensure|consider|address|handle|manage)\b",
        re.IGNORECASE,
    )
    if _VAGUE_TITLE_RE.search(guardrail.title):
        warnings.append(
            f"Guardrail {gid}: title uses vague verb "
            f"('{_VAGUE_TITLE_RE.search(guardrail.title).group()}'). "  # type: ignore[union-attr]
            f"Prefer specific, testable language."
        )

    # Guidance missing normative language
    _NORMATIVE_RE = re.compile(
        r"\b(must|shall|should|may|required|recommended)\b", re.IGNORECASE,
    )
    if not _NORMATIVE_RE.search(guardrail.guidance):
        warnings.append(
            f"Guardrail {gid}: guidance contains no normative language "
            f"(must/should/may). State the rule clearly."
        )

    # Rationale repeats guidance (high overlap)
    if len(guardrail.rationale) > 20 and len(guardrail.guidance) > 20:
        # Simple word-overlap check
        rat_words = set(guardrail.rationale.lower().split())
        guide_words = set(guardrail.guidance.lower().split())
        if len(rat_words) >= 5 and len(guide_words) >= 5:
            overlap = len(rat_words & guide_words) / min(len(rat_words), len(guide_words))
            if overlap > 0.7:
                warnings.append(
                    f"Guardrail {gid}: rationale overlaps heavily with guidance. "
                    f"Rationale should explain why, not restate the rule."
                )

    # Placeholder owner
    _PLACEHOLDER_OWNERS = {"tbd", "todo", "n/a", "unknown", "none", "placeholder", "xxx"}
    if guardrail.owner.lower().strip() in _PLACEHOLDER_OWNERS:
        warnings.append(
            f"Guardrail {gid}: owner is a placeholder ('{guardrail.owner}'). "
            f"Assign an accountable role or team."
        )

    # must severity without references
    if guardrail.severity == "must" and guardrail.status == "active":
        has_refs = references is not None and len(references) > 0
        if not has_refs:
            warnings.append(
                f"Guardrail {gid}: severity is 'must' and status is 'active' "
                f"but no references found. Mandatory rules should cite "
                f"their authoritative source."
            )

    return warnings


@dataclass
class ValidationResult:
    """Collects all validation issues found."""

    errors: list[str] = field(default_factory=lambda: [])
    warnings: list[str] = field(default_factory=lambda: [])

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

    # Check severity vs. text consistency (RFC 2119 keyword conflicts)
    for g in guardrails:
        result.warnings.extend(check_severity_consistency(g))

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
