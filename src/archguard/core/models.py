"""Pydantic models for guardrails, references, links, and I/O contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class Guardrail(BaseModel):
    """A named, scoped architectural constraint."""

    id: str = Field(description="ULID identifier")
    title: str = Field(min_length=1, max_length=200)
    status: Literal["draft", "active", "deprecated", "superseded"]
    severity: Literal["must", "should", "may"]
    rationale: str = Field(min_length=1)
    guidance: str = Field(min_length=1)
    exceptions: str = Field(default="")
    consequences: str = Field(default="")
    scope: list[str] = Field(min_length=1, description="Validated against taxonomy.json at runtime")
    applies_to: list[str] = Field(min_length=1)
    lifecycle_stage: list[str] = Field(default=["acquire", "build", "operate", "retire"])
    owner: str = Field(min_length=1)
    review_date: str | None = Field(default=None, description="ISO 8601 date")
    superseded_by: str | None = Field(default=None)
    created_at: str = Field(description="ISO 8601 datetime")
    updated_at: str = Field(description="ISO 8601 datetime")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Reference(BaseModel):
    """An external citation linking a guardrail to its authoritative source."""

    guardrail_id: str
    ref_type: Literal["adr", "policy", "standard", "regulation", "pattern", "document"]
    ref_id: str
    ref_title: str
    ref_url: str | None = None
    excerpt: str = ""
    added_at: str


class Link(BaseModel):
    """A typed relationship between two guardrails."""

    from_id: str
    to_id: str
    rel_type: Literal["supports", "conflicts", "refines", "implements"]
    note: str = ""


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GuardrailCreate(BaseModel):
    """Input for creating a new guardrail. ID and timestamps are generated server-side."""

    title: str = Field(min_length=1, max_length=200)
    status: Literal["draft", "active", "deprecated", "superseded"] = "draft"
    severity: Literal["must", "should", "may"]
    rationale: str = Field(min_length=1)
    guidance: str = Field(min_length=1)
    exceptions: str = Field(default="")
    consequences: str = Field(default="")
    scope: list[str] = Field(min_length=1)
    applies_to: list[str] = Field(min_length=1)
    lifecycle_stage: list[str] = Field(default=["acquire", "build", "operate", "retire"])
    owner: str = Field(min_length=1)
    review_date: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    references: list[ReferenceCreate] = Field(default_factory=lambda: [])

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
    match_sources: list[Literal["bm25", "vector"]]
    snippet: str


class SearchResponse(BaseModel):
    """Search command output envelope."""

    ok: bool = True
    results: list[SearchResult]
    total: int
    query: str
    filters_applied: dict[str, Any]


class CheckResponse(BaseModel):
    """Check command output envelope."""

    ok: bool = True
    context: dict[str, Any]
    matches: list[SearchResult]
    summary: dict[str, Any]


class ErrorResponse(BaseModel):
    """Structured error envelope."""

    ok: bool = False
    error: dict[str, Any]
