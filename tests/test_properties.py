"""Hypothesis property-based tests for data integrity."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from archguard.core.models import Guardrail

VALID_STATUSES = ["draft", "active", "deprecated", "superseded"]
VALID_SEVERITIES = ["must", "should", "may"]


@given(
    title=st.text(min_size=1, max_size=200),
    status=st.sampled_from(VALID_STATUSES),
    severity=st.sampled_from(VALID_SEVERITIES),
    scope=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    applies_to=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
)
@settings(max_examples=50)
def test_guardrail_roundtrip(
    title: str,
    status: str,
    severity: str,
    scope: list[str],
    applies_to: list[str],
) -> None:
    """Any valid Guardrail can be serialized and deserialized without data loss."""
    import orjson

    g = Guardrail(
        id="01HXR00000000000000000TEST",
        title=title,
        status=status,
        severity=severity,
        rationale="test rationale",
        guidance="test guidance",
        scope=scope,
        applies_to=applies_to,
        owner="Test Team",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )

    serialized = orjson.dumps(g.model_dump())
    deserialized = Guardrail.model_validate(orjson.loads(serialized))
    assert deserialized.title == title
    assert deserialized.status == status
    assert deserialized.severity == severity
    assert deserialized.scope == scope
