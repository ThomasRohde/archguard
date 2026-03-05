"""Tests for Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from archguard.core.models import Guardrail, GuardrailPatch, Link, Reference


class TestGuardrail:
    def test_valid_guardrail(self, sample_guardrail_dict: dict) -> None:
        g = Guardrail.model_validate(sample_guardrail_dict)
        assert g.id == sample_guardrail_dict["id"]
        assert g.severity == "should"

    def test_missing_required_field(self, sample_guardrail_dict: dict) -> None:
        del sample_guardrail_dict["title"]
        with pytest.raises(ValidationError):
            Guardrail.model_validate(sample_guardrail_dict)

    def test_invalid_severity(self, sample_guardrail_dict: dict) -> None:
        sample_guardrail_dict["severity"] = "critical"
        with pytest.raises(ValidationError):
            Guardrail.model_validate(sample_guardrail_dict)

    def test_invalid_status(self, sample_guardrail_dict: dict) -> None:
        sample_guardrail_dict["status"] = "archived"
        with pytest.raises(ValidationError):
            Guardrail.model_validate(sample_guardrail_dict)

    def test_empty_scope_rejected(self, sample_guardrail_dict: dict) -> None:
        sample_guardrail_dict["scope"] = []
        with pytest.raises(ValidationError):
            Guardrail.model_validate(sample_guardrail_dict)

    def test_title_max_length(self, sample_guardrail_dict: dict) -> None:
        sample_guardrail_dict["title"] = "x" * 201
        with pytest.raises(ValidationError):
            Guardrail.model_validate(sample_guardrail_dict)


class TestGuardrailPatch:
    def test_all_none_is_valid(self) -> None:
        patch = GuardrailPatch()
        assert patch.title is None
        assert patch.severity is None

    def test_partial_fields(self) -> None:
        patch = GuardrailPatch(title="Updated title", severity="must")
        assert patch.title == "Updated title"
        assert patch.severity == "must"
        assert patch.scope is None


class TestReference:
    def test_valid_reference(self) -> None:
        ref = Reference(
            guardrail_id="01HXR00000000000000000TEST",
            ref_type="policy",
            ref_id="POL-API-001",
            ref_title="API Governance Policy v2.1",
            ref_url="https://example.com/policy",
            excerpt="All APIs must be registered.",
            added_at="2026-01-15T09:00:00Z",
        )
        assert ref.ref_type == "policy"

    def test_invalid_ref_type(self) -> None:
        with pytest.raises(ValidationError):
            Reference(
                guardrail_id="test",
                ref_type="blog_post",
                ref_id="x",
                ref_title="x",
                added_at="2026-01-01T00:00:00Z",
            )


class TestLink:
    def test_valid_link(self) -> None:
        link = Link(from_id="a", to_id="b", rel_type="supports", note="test")
        assert link.rel_type == "supports"

    def test_invalid_rel_type(self) -> None:
        with pytest.raises(ValidationError):
            Link(from_id="a", to_id="b", rel_type="blocks")
