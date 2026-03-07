"""Integrity checks for JSONL data (used by `guardrails validate`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from archguard.core.models import Guardrail, Reference
from archguard.core.public_ids import display_guardrail_id
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
_QUOTE_CHARS_BEFORE = frozenset({'"', "'", "`", "\u201c", "\u2018"})
_QUOTE_CHARS_AFTER = frozenset({'"', "'", "`", "\u201d", "\u2019"})
_NORMATIVE_RE = re.compile(
    r"\b(must|shall|should|may|required|recommended)\b", re.IGNORECASE,
)
_METALINGUISTIC_CONTEXT_RE = re.compile(
    r"\b(errors?|error\s+messages?|message(?:s)?|word(?:ing|ed|s)?|phrase(?:s|d|ing)?|"
    r"term(?:s)?|vocabulary|text|copy|string(?:s)?|keyword(?:s)?|label(?:s)?)\b",
    re.IGNORECASE,
)
_METALINGUISTIC_CUE_RE = re.compile(
    r"\b(use|using|include|including|contain(?:s|ing)?|return|emit|say|says|"
    r"word(?:ed|ing)?|phrase(?:d|ing)?|quote(?:d)?|label(?:led|ing)?)\b",
    re.IGNORECASE,
)
_IMPERATIVE_GUIDANCE_RE = re.compile(
    (
        r"^\s*(?:[-*]\s+|\d+\.\s+)?"
        r"(do\s+not|don't|never|always|only|avoid|prefer|use|adopt|configure|"
        r"enable|disable|encrypt|rotate|store|run|deploy|route|document|approve|"
        r"require|validate|authenticate|authorize|restrict|pin|separate|emit|log|"
        r"keep|treat|register|provision|monitor|backup|retain|classify|protect|"
        r"segment|isolate|standardize|centralize|review|record|publish|scan|"
        r"terminate|expose|maintain|map|label)\b"
    ),
    re.IGNORECASE,
)

PLACEHOLDER_OWNERS = {
    "tbd",
    "todo",
    "n/a",
    "unknown",
    "none",
    "placeholder",
    "xxx",
    "unassigned",
}


def owner_is_placeholder(owner: str) -> bool:
    """Return True when owner is a neutral placeholder rather than accountable ownership."""
    return owner.lower().strip() in PLACEHOLDER_OWNERS


def has_reference_evidence(references: list[Reference] | None) -> bool:
    """Return True if any reference preserves non-empty evidence text."""
    if not references:
        return False
    return any(bool(getattr(ref, "excerpt", "").strip()) for ref in references)


def check_active_guardrail_requirements(
    guardrail: Guardrail,
    references: list[Reference] | None = None,
) -> list[str]:
    """Return hard policy issues for guardrails that claim active status."""
    if guardrail.status != "active":
        return []

    issues: list[str] = []
    gid = display_guardrail_id(guardrail)

    if not references:
        issues.append(
            f"Guardrail {gid}: status is 'active' but no references found."
        )
    elif not has_reference_evidence(references):
        issues.append(
            f"Guardrail {gid}: status is 'active' but no reference excerpt "
            f"preserves the source evidence."
        )

    if owner_is_placeholder(guardrail.owner):
        issues.append(
            f"Guardrail {gid}: status is 'active' but owner is a placeholder ('{guardrail.owner}')."
        )

    return issues


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
            if match and not _is_metalinguistic_keyword_use(text, match.start(), match.end()):
                warnings.append(
                    f"Guardrail {display_guardrail_id(guardrail)} ({guardrail.severity}): "
                    f"{field_name} contains '{match.group()}' "
                    f"(conflicting {label} language)"
                )
    return warnings


def _is_metalinguistic_keyword_use(text: str, start: int, end: int) -> bool:
    """Return True when a matched RFC 2119 keyword is being discussed as vocabulary.

    Example: "Validation errors should use must, must not, and may not".
    """
    fragment_start = max(text.rfind(boundary, 0, start) for boundary in ".!?\n") + 1
    fragment_end_candidates = [text.find(boundary, end) for boundary in ".!?\n"]
    valid_fragment_ends = [candidate for candidate in fragment_end_candidates if candidate != -1]
    fragment_end = min(valid_fragment_ends) if valid_fragment_ends else len(text)
    fragment = text[fragment_start:fragment_end]

    if not _METALINGUISTIC_CONTEXT_RE.search(fragment):
        return False

    prefix = fragment[: max(0, start - fragment_start)]
    if _METALINGUISTIC_CUE_RE.search(prefix):
        return True

    quoted_before = start > 0 and text[start - 1] in _QUOTE_CHARS_BEFORE
    quoted_after = end < len(text) and text[end] in _QUOTE_CHARS_AFTER
    return quoted_before and quoted_after


def check_authoring_quality(
    guardrail: Guardrail,
    references: list[Reference] | None = None,
) -> list[str]:
    """Return warnings for common authoring quality issues.

    These are non-fatal: the guardrail is structurally valid but may be
    semantically weak. Designed to help weaker models self-correct.
    """
    warnings: list[str] = []
    gid = display_guardrail_id(guardrail)

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
    if not (
        _NORMATIVE_RE.search(guardrail.guidance)
        or _IMPERATIVE_GUIDANCE_RE.search(guardrail.guidance)
    ):
        warnings.append(
            f"Guardrail {gid}: guidance may be too soft or descriptive. "
            f"Consider making the rule more explicit with normative language "
            f"or clearer imperative wording."
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
    if owner_is_placeholder(guardrail.owner):
        warnings.append(
            f"Guardrail {gid}: owner is a placeholder ('{guardrail.owner}'). "
            f"Assign an accountable role or team."
        )

    # Active guardrails should always cite an authoritative source.
    if guardrail.status == "active":
        has_refs = references is not None and len(references) > 0
        if not has_refs:
            warnings.append(
                f"Guardrail {gid}: status is 'active' but no references found. "
                f"Active guardrails should cite at least one authoritative source."
            )
        elif not has_reference_evidence(references):
            warnings.append(
                f"Guardrail {gid}: status is 'active' but no reference excerpt preserves evidence. "
                f"Active guardrails should include at least one excerpt showing the source rule."
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

    public_ids = [g.public_id for g in guardrails if g.public_id is not None]
    if len(public_ids) != len(set(public_ids)):
        seen_public_ids: set[str] = set()
        for public_id in public_ids:
            if public_id in seen_public_ids:
                result.errors.append(f"Duplicate public guardrail ID: {public_id}")
            seen_public_ids.add(public_id)

    # Validate scope against taxonomy
    if taxonomy:
        for g in guardrails:
            for s in g.scope:
                if s not in taxonomy:
                    result.errors.append(
                        f"Guardrail {display_guardrail_id(g)}: scope '{s}' not in "
                        f"taxonomy. Allowed: {taxonomy}"
                    )

    # Load and check references
    references = []
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

    refs_by_guardrail: dict[str, list[Reference]] = {}
    for ref in references:
        refs_by_guardrail.setdefault(ref.guardrail_id, []).append(ref)

    # Check severity vs. text consistency and authoring quality
    for g in guardrails:
        result.errors.extend(
            check_active_guardrail_requirements(g, refs_by_guardrail.get(g.id, [])),
        )
        result.warnings.extend(check_severity_consistency(g))
        result.warnings.extend(
            check_authoring_quality(g, refs_by_guardrail.get(g.id, [])),
        )

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
