"""Pydantic models for guardrails, references, links, and I/O contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _validate_iso_date(v: str | None) -> str | None:
    """Validate that a string is a valid ISO 8601 date (YYYY-MM-DD)."""
    if v is None:
        return v
    from datetime import date

    try:
        date.fromisoformat(v)
    except (ValueError, TypeError) as e:
        msg = f"Invalid ISO 8601 date: {v!r}"
        raise ValueError(msg) from e
    return v


def _validate_iso_datetime(v: str) -> str:
    """Validate that a string is a valid ISO 8601 datetime."""
    from datetime import datetime

    try:
        datetime.fromisoformat(v)
    except (ValueError, TypeError) as e:
        msg = f"Invalid ISO 8601 datetime: {v!r}"
        raise ValueError(msg) from e
    return v


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class Guardrail(BaseModel):
    """A named, scoped architectural constraint."""

    id: str = Field(..., description="ULID identifier")
    title: str = Field(..., min_length=1, max_length=200)
    status: Literal["draft", "active", "deprecated", "superseded"]
    severity: Literal["must", "should", "may"]
    rationale: str = Field(..., min_length=1)
    guidance: str = Field(..., min_length=1)
    exceptions: str = Field(default="")
    consequences: str = Field(default="")
    scope: list[str] = Field(
        ..., min_length=1, description="Validated against taxonomy.json at runtime",
    )
    applies_to: list[str] = Field(
        ..., min_length=1, description="Free-form tags (not validated against taxonomy)",
    )
    lifecycle_stage: list[str] = Field(default=["acquire", "build", "operate", "retire"])
    owner: str = Field(..., min_length=1)
    review_date: str | None = Field(default=None, description="ISO 8601 date")
    superseded_by: str | None = Field(default=None)
    created_at: str = Field(..., description="ISO 8601 datetime")
    updated_at: str = Field(..., description="ISO 8601 datetime")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("review_date", mode="before")
    @classmethod
    def _validate_review_date(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _validate_timestamps(cls, v: str) -> str:
        return _validate_iso_datetime(v)


class Reference(BaseModel):
    """An external citation linking a guardrail to its authoritative source."""

    guardrail_id: str
    ref_type: Literal["adr", "policy", "standard", "regulation", "pattern", "document"]
    ref_id: str
    ref_title: str
    ref_url: str | None = None
    excerpt: str = ""
    added_at: str

    @field_validator("added_at", mode="before")
    @classmethod
    def _validate_added_at(cls, v: str) -> str:
        return _validate_iso_datetime(v)


class Link(BaseModel):
    """A typed relationship between two guardrails."""

    from_id: str
    to_id: str
    rel_type: Literal["supports", "conflicts", "refines", "implements", "requires"]
    note: str = ""


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GuardrailCreate(BaseModel):
    """Input for creating a new guardrail. ID and timestamps are generated server-side."""

    title: str = Field(..., min_length=1, max_length=200)
    status: Literal["draft", "active", "deprecated", "superseded"] = "draft"
    severity: Literal["must", "should", "may"]
    rationale: str = Field(..., min_length=1)
    guidance: str = Field(..., min_length=1)
    exceptions: str = Field(default="")
    consequences: str = Field(default="")
    scope: list[str] = Field(..., min_length=1)
    applies_to: list[str] = Field(..., min_length=1)
    lifecycle_stage: list[str] = Field(default=["acquire", "build", "operate", "retire"])
    owner: str = Field(..., min_length=1)
    review_date: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    references: list[ReferenceCreate] = Field(default_factory=lambda: [])

    @field_validator("review_date", mode="before")
    @classmethod
    def _validate_review_date(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)

    @classmethod
    def model_json_schema_str(cls) -> str:
        import orjson

        return orjson.dumps(cls.model_json_schema(), option=orjson.OPT_INDENT_2).decode()


class ReferenceCreate(BaseModel):
    """Input for creating a new reference (no guardrail_id — inferred from context)."""

    ref_type: Literal["adr", "policy", "standard", "regulation", "pattern", "document"]
    ref_id: str
    ref_title: str
    ref_url: str | None = None
    excerpt: str = ""


class GuardrailImport(BaseModel):
    """Input for importing a guardrail with optional identity preservation."""

    id: str | None = None
    title: str = Field(..., min_length=1, max_length=200)
    status: Literal["draft", "active", "deprecated", "superseded"] = "draft"
    severity: Literal["must", "should", "may"]
    rationale: str = Field(..., min_length=1)
    guidance: str = Field(..., min_length=1)
    exceptions: str = Field(default="")
    consequences: str = Field(default="")
    scope: list[str] = Field(..., min_length=1)
    applies_to: list[str] = Field(..., min_length=1)
    lifecycle_stage: list[str] = Field(default=["acquire", "build", "operate", "retire"])
    owner: str = Field(..., min_length=1)
    review_date: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("review_date", mode="before")
    @classmethod
    def _validate_review_date(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _validate_timestamps(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_iso_datetime(v)


class GuardrailPatch(BaseModel):
    """Partial update — only provided fields are applied."""

    title: str | None = None
    status: Literal["draft", "active", "deprecated", "superseded"] | None = None
    severity: Literal["must", "should", "may"] | None = None
    rationale: str | None = None
    guidance: str | None = None
    exceptions: str | None = None
    consequences: str | None = None
    scope: list[str] | None = None
    applies_to: list[str] | None = None
    lifecycle_stage: list[str] | None = None
    owner: str | None = None
    review_date: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("review_date", mode="before")
    @classmethod
    def _validate_review_date(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)


# ---------------------------------------------------------------------------
# Check input model
# ---------------------------------------------------------------------------


class CheckContext(BaseModel):
    """Input for checking a decision against the guardrail corpus."""

    decision: str = Field(
        ..., min_length=1, description="The proposed architectural decision to check",
    )
    scope: list[str] = Field(default_factory=list, description="Scope tags to filter by")
    applies_to: list[str] = Field(default_factory=list, description="Applies-to tags to filter by")
    lifecycle_stage: str | None = Field(default=None, description="Lifecycle stage to filter by")
    tags: list[str] = Field(default_factory=list, description="Additional search terms")

    @classmethod
    def model_json_schema_str(cls) -> str:
        import orjson

        return orjson.dumps(cls.model_json_schema(), option=orjson.OPT_INDENT_2).decode()


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class SearchResult(BaseModel):
    """A single search hit returned to the agent."""

    id: str
    title: str
    severity: Literal["must", "should", "may"]
    status: str
    score: float
    relevance: Literal["high", "medium", "low"]
    match_sources: list[Literal["bm25", "vector"]]
    snippet: str


