"""Helpers for immutable user-facing guardrail identifiers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol

PUBLIC_ID_PREFIX = "gr"
PUBLIC_ID_PATTERN = re.compile(r"^gr-(\d{4,})$")


class GuardrailIdentifier(Protocol):
    """Structural type for objects carrying internal and public identifiers."""

    id: str
    public_id: str | None
def validate_public_id(value: str | None) -> str | None:
    """Validate the public guardrail ID format."""
    if value is None:
        return None
    if not PUBLIC_ID_PATTERN.fullmatch(value):
        msg = f"Invalid public guardrail ID: {value!r}. Expected format '{PUBLIC_ID_PREFIX}-0001'."
        raise ValueError(msg)
    return value


def next_public_id(guardrails: Sequence[GuardrailIdentifier]) -> str:
    """Return the next repository-local user-facing guardrail ID."""
    highest = 0
    for guardrail in guardrails:
        public_id = getattr(guardrail, "public_id", None)
        match = PUBLIC_ID_PATTERN.fullmatch(public_id or "")
        if match is None:
            continue
        highest = max(highest, int(match.group(1)))
    return f"{PUBLIC_ID_PREFIX}-{highest + 1:04d}"


def find_guardrail[TGuardrail: GuardrailIdentifier](
    guardrails: Sequence[TGuardrail], identifier: str,
) -> TGuardrail | None:
    """Resolve a guardrail by internal ULID or public ID."""
    return next(
        (g for g in guardrails if g.id == identifier or g.public_id == identifier),
        None,
    )


def find_guardrail_index[TGuardrail: GuardrailIdentifier](
    guardrails: Sequence[TGuardrail], identifier: str,
) -> int | None:
    """Resolve the index of a guardrail by internal ULID or public ID."""
    return next(
        (i for i, g in enumerate(guardrails) if g.id == identifier or g.public_id == identifier),
        None,
    )


def display_guardrail_id(guardrail: GuardrailIdentifier) -> str:
    """Return the preferred human-facing identifier for a guardrail."""
    return guardrail.public_id or guardrail.id[:8]


def display_identifier_value(
    identifier: str | None,
    guardrails_by_id: Mapping[str, GuardrailIdentifier],
) -> str | None:
    """Return a preferred display value for an internal guardrail identifier."""
    if identifier is None:
        return None
    guardrail = guardrails_by_id.get(identifier)
    if guardrail is None:
        return identifier[:8]
    return display_guardrail_id(guardrail)
