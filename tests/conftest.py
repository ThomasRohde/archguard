"""Shared test fixtures for guardrails-cli tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary guardrails data directory with empty JSONL files."""
    data_dir = tmp_path / "guardrails"
    data_dir.mkdir()
    (data_dir / "guardrails.jsonl").touch()
    (data_dir / "references.jsonl").touch()
    (data_dir / "links.jsonl").touch()

    import orjson

    (data_dir / "taxonomy.json").write_bytes(
        orjson.dumps(
            {"scope": ["it-platform", "data-platform", "channels"]}, option=orjson.OPT_INDENT_2
        )
    )
    return data_dir


@pytest.fixture
def sample_guardrail_dict() -> dict:  # type: ignore[type-arg]
    """A valid guardrail dict for testing."""
    return {
        "id": "01HXR00000000000000000TEST",
        "title": "Prefer managed services over self-hosted infrastructure",
        "status": "active",
        "severity": "should",
        "rationale": (
            "Managed services reduce operational burden "
            "and allow teams to focus on business logic."
        ),
        "guidance": (
            "When evaluating infrastructure options, "
            "prefer managed/SaaS offerings over self-hosted alternatives."
        ),
        "exceptions": (
            "Acceptable when regulatory requirements "
            "mandate on-premises hosting."
        ),
        "consequences": (
            "Increased operational cost and staffing requirements "
            "for self-hosted infrastructure."
        ),
        "scope": ["it-platform"],
        "applies_to": ["technology", "platform"],
        "lifecycle_stage": ["acquire"],
        "owner": "Platform Team",
        "review_date": "2026-09-01",
        "superseded_by": None,
        "created_at": "2025-06-15T10:30:00Z",
        "updated_at": "2026-01-20T14:15:00Z",
        "metadata": {},
    }
