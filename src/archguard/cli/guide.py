"""Guide command: machine-readable CLI schema in one call (CLI-MANIFEST §4)."""

from __future__ import annotations

import sys
from typing import Annotated, Any

import typer

from archguard.cli import app, ensure_supported_format, handle_error, state
from archguard.output.json import (
    ERROR_EXIT_MAP,
    SCHEMA_VERSION,
    envelope,
)


def _build_guide(data_dir: str = "guardrails") -> dict[str, Any]:
    """Build the full guide payload — command catalog, error taxonomy, examples."""
    from archguard import __version__

    return {
        "name": "archguard",
        "version": __version__,
        "description": (
            "Architecture guardrails management CLI — a single, queryable "
            "store of architectural constraints, standards, and rules "
            "backed by hybrid BM25 + vector search. AI agents and human "
            "architects ask 'what rules apply to this decision?' and get "
            "ranked, relevant answers. Data lives in Git-friendly JSONL "
            "files. The CLI is deterministic — no LLM inference, no cloud "
            "sync. Agents provide the intelligence; this tool provides "
            "the governance knowledge."
        ),
        "schema_version": SCHEMA_VERSION,
        "compatibility": {
            "additive_changes": "minor",
            "breaking_changes": "major",
        },
        "agent_bootstrap": _agent_bootstrap(),
        "provenance_contract": _provenance_contract(),
        "minimum_evidence": _minimum_evidence(),
        "defaulting_policy": _defaulting_policy(),
        "vocabulary": _vocabulary(data_dir),
        "field_semantics": _field_semantics(),
        "capture_workflow": _capture_workflow(),
        "quality_criteria": _quality_criteria(),
        "anti_patterns": _anti_patterns(),
        "when_not_to_infer": _when_not_to_infer(),
        "when_not_to_add": _when_not_to_add(),
        "global_options": {
            "--format, -f": {
                "type": "string",
                "values": ["json", "table", "markdown"],
                "default": "json",
                "description": (
                    "Output format. json wraps in structured envelope; "
                    "table/markdown are human-readable where implemented. "
                    "Commands without human-readable renderers return "
                    "ERR_VALIDATION_FORMAT instead of silently falling back to JSON."
                ),
            },
            "--quiet, -q": {
                "type": "bool",
                "default": False,
                "description": "Suppress stderr progress messages.",
            },
            "--explain": {
                "type": "bool",
                "default": False,
                "description": (
                    "Print a human-readable description of the command "
                    "to stderr and exit. Does not pollute stdout."
                ),
            },
            "--data-dir, -d": {
                "type": "string",
                "default": "guardrails",
                "description": "Path to guardrails data directory.",
            },
        },
        "environment": {
            "LLM": {
                "values": ["true"],
                "effect": (
                    "Forces JSON output, sets --quiet, suppresses ANSI "
                    "decoration. Recognised per the LLM=true convention."
                ),
            },
        },
        "commands": _commands(),
        "error_codes": _error_codes(),
        "exit_codes": {
            "0": "Success",
            "1": "General/unspecified error",
            "2": "Usage error (bad arguments, missing required options)",
            "10": "Not found (guardrail, reference, or link does not exist)",
            "11": "Already exists (duplicate ID or title on add)",
            "12": "Invalid transition (unsupported status change)",
            "20": "Validation error (input/schema/taxonomy validation failure)",
            "21": "Integrity error (broken links, orphan references, JSONL integrity)",
            "30": "Build error (SQLite index build failure)",
            "31": "Model error (embedding model missing or failed to load)",
            "40": "I/O error (file read/write failure)",
            "50": "Internal error (bug)",
        },
        "envelope_schema": {
            "schema_version": "string — always present",
            "request_id": "string — unique per invocation (ULID-based)",
            "ok": "bool — check this first",
            "command": "string — dotted/hyphenated command ID",
            "result": (
                "object|null — command-specific payload; null on failure"
            ),
            "errors": (
                "array — structured errors "
                "[{code, message, retryable, suggested_action, details?}]; "
                "empty on success"
            ),
            "warnings": "array — non-fatal string messages; always present",
            "metrics": "object — {duration_ms: int}; always present",
        },
        "concurrency": {
            "rule": (
                "Never run multiple write commands on the same "
                "data directory in parallel."
            ),
            "safe_patterns": [
                (
                    "Read commands (search, get, list, related, check, "
                    "stats, review-due) can run in parallel freely."
                ),
                (
                    "Write commands to DIFFERENT data directories "
                    "can run in parallel."
                ),
                "Chain writes to the SAME data directory sequentially.",
            ],
        },
        "examples": _examples(),
        "good_and_bad_examples": _good_and_bad_examples(),
    }


def _vocabulary(data_dir: str) -> dict[str, Any]:
    """Canonical vocabulary — all allowed enum values in one place."""
    from pathlib import Path

    from archguard.core.store import load_taxonomy

    vocab: dict[str, Any] = {
        "severity": ["must", "should", "may"],
        "status": ["draft", "active", "deprecated", "superseded"],
        "ref_type": ["adr", "policy", "standard", "regulation", "pattern", "document"],
        "rel_type": ["supports", "conflicts", "refines", "implements", "requires"],
        "lifecycle_stage": ["acquire", "build", "operate", "retire"],
    }

    taxonomy = load_taxonomy(Path(data_dir))
    if taxonomy:
        vocab["scope"] = {
            "source": "taxonomy.json",
            "values": taxonomy,
            "rule": "Use only these values. Do not invent scope labels.",
        }
    else:
        vocab["scope"] = {
            "source": "unconstrained",
            "values": [],
            "rule": (
                "No taxonomy configured — scope is free-form. "
                "Use consistent, lowercase, hyphenated labels."
            ),
        }

    return vocab


def _agent_bootstrap() -> dict[str, Any]:
    """Deterministic workflow for agents to follow before writing."""
    return {
        "instruction": (
            "Call 'archguard guide' once and cache the result. "
            "Before creating a guardrail, always follow the workflow below."
        ),
        "first_call": "archguard guide",
        "before_create": [
            "archguard search <topic>  — detect duplicates and overlaps",
            "archguard deduplicate     — check corpus-wide similarity",
            "archguard add --schema    — fetch the exact input contract",
        ],
        "writes_are_sequential": True,
        "prefer_draft": [
            "Set status=draft when the source is not clearly authoritative.",
            (
                "Set status=draft when severity, scope, owner, lifecycle_stage, "
                "or review_date must be inferred or defaulted."
            ),
            "Set status=draft when no source excerpt can be cited for the rule.",
            (
                "Only set status=active when the rule is clearly supported by an "
                "authoritative source and at least one evidence-bearing reference is attached."
            ),
        ],
    }


def _provenance_contract() -> dict[str, Any]:
    """Describe which fields come from the source versus agent judgment."""
    return {
        "principle": (
            "Never present inferred or defaulted values as if they were stated by the source."
        ),
        "field_classes": {
            "source_derived": [
                "references",
                "reference excerpts",
                "source identifiers",
                "source normative language",
            ],
            "normalized_from_source": [
                "title",
                "guidance",
                "rationale",
                "severity",
            ],
            "inferred_or_defaulted": [
                "owner",
                "scope",
                "applies_to",
                "lifecycle_stage",
                "review_date",
                "metadata",
            ],
        },
        "rules": [
            "If a field is inferred or defaulted, record that fact in metadata.",
            (
                "Do not invent precise governance metadata unless the source states it "
                "or repository policy supplies it."
            ),
            "If key governance fields are inferred, prefer status=draft.",
        ],
        "metadata_convention": {
            "recommended_shape": {
                "field_derivation": {
                    "owner": "defaulted|inferred|source",
                    "scope": "source|inferred",
                    "review_date": "source|policy|unset",
                }
            },
            "note": (
                "metadata is extensible. Use it to record provenance/defaulting decisions "
                "without changing the core record shape."
            ),
        },
    }


def _minimum_evidence() -> dict[str, Any]:
    """Describe what evidence is expected for draft vs active guardrails."""
    return {
        "active_guardrail_requires": [
            "At least one authoritative reference.",
            "At least one source excerpt showing the evidence for the rule.",
            "Severity justified by the source wording, not model confidence.",
            "A non-placeholder owner accountable for the active rule.",
        ],
        "draft_guardrail_allows": [
            "Incomplete scope.",
            "Placeholder owner such as 'unassigned'.",
            "Missing review_date.",
            "Inferred applies_to tags.",
        ],
    }


def _defaulting_policy() -> dict[str, str]:
    """Guidance for fields that often pressure agents into false precision."""
    return {
        "owner": (
            "Do not infer a specific owner from generic source material. If the source does "
            "not name an accountable owner, keep the record draft and use a neutral placeholder "
            "such as 'unassigned'."
        ),
        "review_date": (
            "Do not invent a specific review date from source material. Only set review_date "
            "from repository policy or human input."
        ),
        "scope": (
            "Use source-aligned scope only when the mapping is obvious. Otherwise choose the "
            "broadest valid scope and keep status=draft."
        ),
        "lifecycle_stage": (
            "Only assign lifecycle stages that are directly supported by the source or clearly "
            "implied by the rule."
        ),
    }


def _field_semantics() -> dict[str, Any]:
    """Domain-level meaning of key fields — not just types, but judgment rules."""
    return {
        "severity": {
            "must": (
                "Mandatory rule. Use ONLY when the source is authoritative "
                "(policy, standard, regulation, formal platform requirement) "
                "and non-compliance requires exception or remediation."
            ),
            "should": (
                "Strong recommendation or default standard. "
                "Deviations require documented rationale."
            ),
            "may": (
                "Optional or advisory practice. "
                "Informational, not enforced."
            ),
            "judgment_rule": (
                "Severity must not exceed the strength of the source. "
                "If the source says 'consider' or 'recommend', "
                "do not assign 'must'."
            ),
        },
        "status": {
            "draft": (
                "Candidate guardrail. Use when wording, scope, or "
                "authority is still being validated."
            ),
            "active": (
                "Current approved guardrail. Requires authoritative references, at least one "
                "evidence-bearing excerpt, and non-placeholder governance metadata."
            ),
            "deprecated": (
                "Retained for audit trail, but no longer preferred. "
                "Use 'deprecate' command."
            ),
            "superseded": (
                "Replaced by another guardrail. "
                "Use 'supersede' command."
            ),
        },
        "scope": (
            "Architectural domain from taxonomy.json. If taxonomy.json is empty, "
            "scope is free-form. Use 'archguard init --taxonomy <file>' to bootstrap "
            "a controlled vocabulary, or inspect taxonomy.json for allowed values."
        ),
        "applies_to": (
            "Free-form tags describing what the guardrail applies to "
            "(e.g. 'technology', 'data', 'integration'). "
            "Not validated against taxonomy."
        ),
        "owner": (
            "Person or team accountable for the rule. Keep owner required in the add contract, "
            "but do not invent false precision: when the source does not name an owner, use a "
            "neutral placeholder such as 'unassigned' and keep status=draft."
        ),
        "review_date": (
            "Next scheduled review date. Optional. Only set it from repository policy or human "
            "input; do not infer a calendar date from generic source material."
        ),
        "lifecycle_stage": (
            "When in the lifecycle the guardrail applies. Defaults exist for convenience, but "
            "narrow values should only be assigned when the source clearly supports them."
        ),
        "references": (
            "External citations linking a guardrail to its authoritative "
            "source. Active guardrails must have at least one authoritative reference and at "
            "least one excerpt showing the evidence for the rule. Types: adr, policy, standard, "
            "regulation, pattern, document."
        ),
        "title": (
            "States the rule, not the rationale. "
            "Concise, normative, one rule per title. "
            "Bad: 'Security considerations'. "
            "Good: 'Encrypt data at rest with AES-256'."
        ),
        "guidance": (
            "Actionable instruction — what to do in concrete terms. "
            "Bad: 'Follow best practices'. "
            "Good: 'Use the platform TLS termination proxy for all "
            "external-facing services'."
        ),
        "rationale": (
            "Explains why the rule exists. Provides context, "
            "not the rule itself."
        ),
    }


def _capture_workflow() -> list[str]:
    """Step-by-step process for extracting a guardrail from source material."""
    return [
        "1. Search for existing overlapping guardrails (archguard search <topic>).",
        (
            "2. Extract candidate normative statements from the source. Ignore background "
            "context unless it implies a clear rule."
        ),
        "3. Keep ONE atomic rule only.",
        "4. Record the source evidence: reference, excerpt, section, or quote span.",
        "5. Choose severity based on source wording, not model confidence.",
        "6. Classify each field as source-derived, normalized, inferred, or defaulted.",
        "7. If key fields are inferred or evidence is weak, set status=draft.",
        "8. Write a normative title (states the rule, not the topic).",
        "9. Write actionable guidance (what to do, not 'follow best practices').",
        "10. Write rationale (why the rule exists).",
        "11. Attach references and evidence (archguard ref-add).",
        "12. Create the guardrail (archguard add).",
        "13. Link, supersede, or deprecate related records if needed.",
    ]


def _quality_criteria() -> list[str]:
    """What makes a good guardrail record."""
    return [
        "One atomic rule per record.",
        "Title is normative and concise — states the rule, not the topic.",
        "Guidance is actionable and specific — concrete instructions.",
        "Rationale explains why the rule exists.",
        "Severity does not exceed source strength.",
        "Active guardrails have at least one authoritative reference.",
        "Active guardrails include evidence such as an excerpt or section pointer text.",
        "Inferred/defaulted fields are clearly marked in metadata.",
        "Owner and review_date are not invented from non-governance source material.",
        "Scope and applies_to are specific, not overly broad.",
        "No duplicate or near-duplicate of an existing guardrail.",
    ]


def _anti_patterns() -> list[str]:
    """Common mistakes when creating guardrails."""
    return [
        "Vague guidance like 'follow best practices' or 'ensure compliance'.",
        "Compound rule covering multiple unrelated concerns in one record.",
        "Using severity=must without authoritative evidence from the source.",
        "Creating a new guardrail when an existing one should be updated or linked.",
        "Capturing implementation detail as if it were architecture policy.",
        "Title that describes a topic area rather than stating a rule.",
        "Rationale that repeats the guidance instead of explaining the 'why'.",
        "Setting status=active without attaching references.",
        "Assigning a specific owner when the source does not identify one.",
        "Inventing a precise review date with no repository policy or human input.",
        (
            "Populating scope, lifecycle_stage, or applies_to with narrow labels that are not "
            "supported by the source."
        ),
        "Setting status=active when the record depends heavily on inference.",
        "Using a reference URL without preserving the evidence excerpt that justified the rule.",
    ]


def _when_not_to_infer() -> list[dict[str, str]]:
    """Fields where false precision is especially harmful."""
    return [
        {
            "field": "owner",
            "rule": (
                "Do not infer a team owner from a generic industry source, vendor guide, or "
                "architecture article."
            ),
        },
        {
            "field": "review_date",
            "rule": "Do not invent a calendar date unless repository policy defines one.",
        },
        {
            "field": "severity",
            "rule": "Do not upgrade advisory language to mandatory language.",
        },
        {
            "field": "scope",
            "rule": "Do not map to a narrow domain label unless the mapping is obvious.",
        },
    ]


def _when_not_to_add() -> list[dict[str, str]]:
    """Situations where a guardrail should NOT be created."""
    return [
        {
            "situation": "Source is background context, not a normative rule.",
            "instead": "Use ref-add to attach the source to an existing guardrail.",
        },
        {
            "situation": "Source is an implementation example, not a policy.",
            "instead": "Do not create a guardrail. Implementation details are not governance.",
        },
        {
            "situation": "An existing guardrail already covers this rule.",
            "instead": "Use update to refine the existing record, or link to connect them.",
        },
        {
            "situation": "The rule is a specialization of an existing guardrail.",
            "instead": "Create the new guardrail and link it with rel_type=refines.",
        },
        {
            "situation": "Source uses vague language with no clear normative action.",
            "instead": "Do not create a guardrail. Not every statement is a rule.",
        },
        {
            "situation": "The content is a relationship between existing guardrails.",
            "instead": "Use link to express the relationship (supports, conflicts, etc.).",
        },
    ]


def _good_and_bad_examples() -> list[dict[str, Any]]:
    """Semantic examples showing good vs bad guardrail capture."""
    return [
        {
            "label": "Atomic vs compound rule",
            "bad": {
                "title": "API security and performance standards",
                "guidance": (
                    "APIs must use OAuth 2.0 for auth and must respond "
                    "within 200ms at p99."
                ),
                "problem": "Two unrelated rules in one record.",
            },
            "good": [
                {
                    "title": "Authenticate APIs with OAuth 2.0",
                    "guidance": (
                        "All external-facing APIs must authenticate "
                        "requests using OAuth 2.0 with the platform "
                        "identity provider."
                    ),
                },
                {
                    "title": "API response latency below 200ms at p99",
                    "guidance": (
                        "External-facing APIs should respond within "
                        "200ms at the 99th percentile under normal load."
                    ),
                },
            ],
        },
        {
            "label": "Severity matching source strength",
            "bad": {
                "title": "Consider event-driven integration",
                "severity": "must",
                "source_says": "Teams should consider event-driven patterns.",
                "problem": (
                    "Source uses 'should consider' (advisory) but "
                    "guardrail claims 'must' (mandatory)."
                ),
            },
            "good": {
                "title": "Prefer event-driven integration for async workflows",
                "severity": "should",
                "source_says": "Teams should consider event-driven patterns.",
            },
        },
        {
            "label": "Normative title vs topic title",
            "bad": {
                "title": "Data encryption",
                "problem": "Describes a topic, not a rule.",
            },
            "good": {
                "title": "Encrypt data at rest with AES-256 or equivalent",
            },
        },
        {
            "label": "Actionable guidance vs vague guidance",
            "bad": {
                "guidance": "Follow industry best practices for logging.",
                "problem": "Not actionable — what are the 'best practices'?",
            },
            "good": {
                "guidance": (
                    "Emit structured JSON logs to stdout. Include "
                    "correlation_id, timestamp, level, and service_name "
                    "in every log entry."
                ),
            },
        },
        {
            "label": "False precision in metadata",
            "bad": {
                "title": "Implement centralized incident response processes",
                "owner": "Security Architecture",
                "review_date": "2026-12-31",
                "problem": (
                    "The source does not identify an owner or review date. "
                    "These values were invented."
                ),
            },
            "good": {
                "title": "Implement centralized incident response processes",
                "owner": "unassigned",
                "status": "draft",
                "metadata": {
                    "field_derivation": {
                        "owner": "defaulted",
                        "review_date": "unset",
                        "scope": "inferred",
                    }
                },
            },
        },
        {
            "label": "Reference without evidence",
            "bad": {
                "references": [
                    {
                        "ref_type": "document",
                        "ref_title": "Security checklist",
                        "ref_url": "https://example.com/checklist",
                    }
                ],
                "problem": (
                    "The source is linked, but the specific evidence for the rule is not preserved."
                ),
            },
            "good": {
                "references": [
                    {
                        "ref_type": "document",
                        "ref_title": "Security checklist",
                        "ref_url": "https://example.com/checklist",
                        "excerpt": (
                            "Use a secure development lifecycle supported by "
                            "threat modeling practices."
                        ),
                    }
                ]
            },
        },
    ]


def _commands() -> dict[str, Any]:
    """Command catalog grouped by read/write/maintenance."""
    return {
        "init": {
            "group": "setup",
            "mutates": True,
            "description": (
                "Create guardrails data directory, JSONL files, "
                "taxonomy, and .gitignore. Unless --taxonomy is provided, "
                "taxonomy.json is created with an empty scope array (free-form mode). "
                "Search index warm-up happens lazily on first add/search/build."
            ),
            "args": [],
            "flags": ["--taxonomy PATH", "--explain", "--schema"],
            "stdin": None,
            "result_fields": ["message", "path"],
        },
        "build": {
            "group": "setup",
            "mutates": True,
            "description": "Rebuild SQLite index from JSONL files.",
            "args": [],
            "flags": ["--force", "--explain"],
            "stdin": None,
            "result_fields": [
                "message", "guardrails", "references",
                "links", "embeddings",
            ],
        },
        "validate": {
            "group": "setup",
            "mutates": False,
            "description": (
                "Check JSONL integrity, broken links, "
                "and orphan references."
            ),
            "args": [],
            "flags": ["--explain"],
            "stdin": None,
            "result_fields": ["errors", "warnings"],
        },
        "search": {
            "group": "read",
            "mutates": False,
            "description": (
                "Hybrid BM25 + vector search across guardrails, "
                "ranked by RRF. Deprecated and superseded guardrails are "
                "excluded by default."
            ),
            "args": ["QUERY"],
            "flags": [
                "--status", "--severity", "--scope", "--applies-to",
                "--lifecycle-stage", "--owner", "--include-historical", "--top N",
                "--min-score FLOAT", "--explain",
            ],
            "stdin": None,
            "result_fields": [
                "results[]", "total", "query", "filters_applied",
            ],
        },
        "get": {
            "group": "read",
            "mutates": False,
            "description": (
                "Get full detail for a guardrail including "
                "references and links."
            ),
            "args": ["GUARDRAIL_ID"],
            "flags": ["--explain"],
            "stdin": None,
            "result_fields": ["guardrail", "references[]", "links[]"],
        },
        "list": {
            "group": "read",
            "mutates": False,
            "description": (
                "List guardrails with optional filters "
                "(no full-text search)."
            ),
            "args": [],
            "flags": [
                "--status", "--severity", "--scope", "--applies-to",
                "--lifecycle-stage", "--owner", "--review-before DATE",
                "--top N", "--explain",
            ],
            "stdin": None,
            "result_fields": ["guardrails[]", "total"],
        },
        "related": {
            "group": "read",
            "mutates": False,
            "description": (
                "Show linked guardrails with relationship types."
            ),
            "args": ["GUARDRAIL_ID"],
            "flags": ["--explain"],
            "stdin": None,
            "result_fields": ["guardrail_id", "related[]"],
        },
        "check": {
            "group": "read",
            "mutates": False,
            "description": (
                "Check a proposed decision against the guardrail "
                "corpus. Reads context JSON from stdin. Deprecated and "
                "superseded guardrails are excluded by default."
            ),
            "args": [],
            "flags": ["--status", "--include-historical", "--explain", "--schema"],
            "stdin": {
                "format": "JSON",
                "required_fields": ["decision"],
                "optional_fields": [
                    "scope[]", "applies_to[]",
                    "lifecycle_stage", "tags[]",
                ],
            },
            "result_fields": ["context", "matches[]", "summary", "filters_applied"],
        },
        "add": {
            "group": "write",
            "mutates": True,
            "description": (
                "Add a new guardrail from JSON on stdin. "
                "Optionally includes inline references."
            ),
            "args": [],
            "flags": ["--explain", "--schema"],
            "stdin": {
                "format": "JSON",
                "required_fields": [
                    "title", "severity", "rationale", "guidance",
                    "scope[]", "applies_to[]", "owner",
                ],
                "optional_fields": [
                    "status", "exceptions", "consequences",
                    "lifecycle_stage[]", "review_date",
                    "metadata{}", "references[]",
                ],
            },
            "result_fields": ["guardrail", "references[]"],
        },
        "update": {
            "group": "write",
            "mutates": True,
            "description": (
                "Partially update a guardrail with patch semantics. "
                "Reads patch JSON from stdin."
            ),
            "args": ["GUARDRAIL_ID"],
            "flags": ["--explain"],
            "stdin": {
                "format": "JSON",
                "description": (
                    "Partial patch — only provided fields are changed."
                ),
                "optional_fields": [
                    "title", "status", "severity", "rationale",
                    "guidance", "exceptions", "consequences",
                    "scope[]", "applies_to[]", "lifecycle_stage[]",
                    "owner", "review_date", "metadata{}",
                ],
            },
            "result_fields": ["guardrail"],
        },
        "ref-add": {
            "group": "write",
            "mutates": True,
            "description": (
                "Add a reference/citation to an existing guardrail. "
                "Reads reference JSON from stdin."
            ),
            "args": ["GUARDRAIL_ID"],
            "flags": ["--explain"],
            "stdin": {
                "format": "JSON",
                "required_fields": [
                    "ref_type", "ref_id", "ref_title",
                ],
                "optional_fields": ["ref_url", "excerpt"],
            },
            "result_fields": ["reference"],
        },
        "link": {
            "group": "write",
            "mutates": True,
            "description": (
                "Create a typed relationship between two guardrails."
            ),
            "args": ["FROM_ID", "TO_ID"],
            "flags": [
                "--rel TYPE (supports|conflicts|refines|implements|requires)",
                "--note TEXT",
                "--explain",
            ],
            "stdin": None,
            "result_fields": ["link"],
        },
        "delete": {
            "group": "write",
            "mutates": True,
            "description": (
                "Permanently delete a guardrail and its "
                "associated references and links. "
                "Requires --confirm (auto-confirmed when LLM=true)."
            ),
            "args": ["GUARDRAIL_ID"],
            "flags": ["--confirm", "--explain"],
            "stdin": None,
            "result_fields": ["deleted", "references_removed", "links_removed"],
        },
        "deprecate": {
            "group": "write",
            "mutates": True,
            "description": "Mark a guardrail as deprecated.",
            "args": ["GUARDRAIL_ID"],
            "flags": ["--reason TEXT", "--explain"],
            "stdin": None,
            "result_fields": ["guardrail"],
        },
        "supersede": {
            "group": "write",
            "mutates": True,
            "description": (
                "Mark a guardrail as superseded by another, "
                "creating an 'implements' link."
            ),
            "args": ["GUARDRAIL_ID"],
            "flags": ["--by REPLACEMENT_ID", "--explain"],
            "stdin": None,
            "result_fields": ["guardrail", "link"],
        },
        "stats": {
            "group": "maintenance",
            "mutates": False,
            "description": (
                "Show counts by status, severity, scope, "
                "and staleness."
            ),
            "args": [],
            "flags": ["--explain"],
            "stdin": None,
            "result_fields": [
                "total", "by_status{}", "by_severity{}",
                "by_scope{}", "stale",
            ],
        },
        "review-due": {
            "group": "maintenance",
            "mutates": False,
            "description": (
                "List guardrails past or approaching "
                "their review date."
            ),
            "args": [],
            "flags": ["--before DATE", "--explain"],
            "stdin": None,
            "result_fields": ["cutoff", "guardrails[]", "total"],
        },
        "deduplicate": {
            "group": "maintenance",
            "mutates": False,
            "description": (
                "Detect likely duplicate guardrails via "
                "hybrid FTS + vector similarity. The default threshold is tuned "
                "for short, normative guardrails."
            ),
            "args": [],
            "flags": ["--threshold FLOAT", "--explain"],
            "stdin": None,
            "result_fields": ["pairs[]", "total", "threshold"],
        },
        "import": {
            "group": "maintenance",
            "mutates": True,
            "description": (
                "Bulk upsert guardrails from a JSON array, a full-fidelity JSON snapshot, "
                "or a CSV file."
            ),
            "args": ["FILE"],
            "flags": ["--explain"],
            "stdin": None,
            "result_fields": [
                "imported", "updated", "references_imported", "links_imported", "errors[]",
            ],
        },
        "export": {
            "group": "maintenance",
            "mutates": False,
            "description": (
                "Export guardrails in JSON, CSV, or Markdown format. JSON is a "
                "full-fidelity snapshot including references and links. "
                "CSV and Markdown are publishing views. "
                "When LLM=true, all formats return the standard JSON "
                "envelope with result.content (string) and result.format."
            ),
            "args": [],
            "flags": [
                "--format TYPE", "--status", "--severity",
                "--scope", "--explain",
            ],
            "stdin": None,
            "result_fields": [
                "fidelity", "guardrails[]", "references[]", "links[]", "content", "format",
            ],
        },
        "guide": {
            "group": "meta",
            "mutates": False,
            "description": (
                "Return the full CLI schema as JSON — commands, "
                "flags, error codes, examples."
            ),
            "args": [],
            "flags": [],
            "stdin": None,
            "result_fields": ["(this entire payload)"],
        },
    }


def _error_codes() -> dict[str, Any]:
    """Error code taxonomy with exit codes, retry hints, and descriptions."""
    return {
        "ERR_RESOURCE_NOT_FOUND": {
            "exit_code": ERROR_EXIT_MAP["ERR_RESOURCE_NOT_FOUND"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "The requested guardrail, reference, or link "
                "does not exist."
            ),
        },
        "ERR_VALIDATION": {
            "exit_code": ERROR_EXIT_MAP["ERR_VALIDATION"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "Generic validation failure "
                "(schema, field constraint, taxonomy mismatch)."
            ),
        },
        "ERR_VALIDATION_JSON": {
            "exit_code": ERROR_EXIT_MAP["ERR_VALIDATION_JSON"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": "Input is not valid JSON.",
        },
        "ERR_VALIDATION_INPUT": {
            "exit_code": ERROR_EXIT_MAP["ERR_VALIDATION_INPUT"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "A required input field is missing "
                "or has the wrong type."
            ),
        },
        "ERR_VALIDATION_FORMAT": {
            "exit_code": ERROR_EXIT_MAP["ERR_VALIDATION_FORMAT"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "Unsupported file format or output format requested."
            ),
        },
        "ERR_VALIDATION_SCHEMA": {
            "exit_code": ERROR_EXIT_MAP["ERR_VALIDATION_SCHEMA"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "Input does not conform to the expected schema."
            ),
        },
        "ERR_INTEGRITY": {
            "exit_code": ERROR_EXIT_MAP["ERR_INTEGRITY"],
            "retryable": False,
            "suggested_action": "fix_data",
            "description": (
                "Repository data integrity failed "
                "(broken links, orphan references, malformed JSONL)."
            ),
        },
        "ERR_CONFLICT_EXISTS": {
            "exit_code": ERROR_EXIT_MAP["ERR_CONFLICT_EXISTS"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "A resource with the same identity "
                "(e.g. title) already exists."
            ),
        },
        "ERR_CONFLICT_TRANSITION": {
            "exit_code": ERROR_EXIT_MAP["ERR_CONFLICT_TRANSITION"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "The requested status transition is not allowed "
                "(e.g. deprecating a superseded guardrail)."
            ),
        },
        "ERR_IO_FILE_NOT_FOUND": {
            "exit_code": ERROR_EXIT_MAP["ERR_IO_FILE_NOT_FOUND"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": "A referenced file path does not exist.",
        },
        "ERR_IO_FORMAT": {
            "exit_code": ERROR_EXIT_MAP["ERR_IO_FORMAT"],
            "retryable": False,
            "suggested_action": "fix_input",
            "description": (
                "Unsupported file extension for I/O operation."
            ),
        },
        "ERR_BUILD": {
            "exit_code": ERROR_EXIT_MAP["ERR_BUILD"],
            "retryable": True,
            "suggested_action": "retry",
            "description": "SQLite index build failed.",
        },
        "ERR_MODEL": {
            "exit_code": ERROR_EXIT_MAP["ERR_MODEL"],
            "retryable": False,
            "suggested_action": "fix_environment",
            "description": "Embedding model is unavailable or failed to load.",
        },
        "ERR_INTERNAL": {
            "exit_code": ERROR_EXIT_MAP["ERR_INTERNAL"],
            "retryable": False,
            "suggested_action": "escalate",
            "description": (
                "Internal error — likely a bug. Do not retry."
            ),
        },
    }


def _examples() -> list[dict[str, Any]]:
    """Concrete usage examples for common workflows."""
    posix_add_example = (
        "echo '{\"title\":\"Prefer managed services\","
        "\"severity\":\"should\","
        "\"rationale\":\"Reduce ops burden\","
        "\"guidance\":\"Use managed offerings\","
        "\"scope\":[\"it-platform\"],"
        "\"applies_to\":[\"technology\"],"
        "\"owner\":\"Platform Team\"}' | archguard add"
    )
    powershell_add_example = "Get-Content .\\g.json | archguard add"
    posix_check_example = (
        "echo '{\"decision\":\"Use self-hosted Kafka\","
        "\"scope\":[\"it-platform\"],"
        "\"tags\":[\"kafka\"]}' | archguard check"
    )
    powershell_check_example = "Get-Content .\\decision.json | archguard check"
    posix_update_example = (
        "echo '{\"severity\":\"must\","
        "\"guidance\":\"Updated guidance\"}'"
        " | archguard update 01HXYZ..."
    )
    powershell_update_example = "Get-Content .\\patch.json | archguard update 01HXYZ..."
    powershell_ref_add_example = "Get-Content .\\reference.json | archguard ref-add 01HXYZ..."
    return [
        {
            "title": "Bootstrap a new guardrails repository",
            "commands": [
                "archguard init --taxonomy taxonomy.json",
                "archguard build",
            ],
        },
        {
            "title": "Add a guardrail",
            "commands": [posix_add_example],
            "powershell_commands": [powershell_add_example],
        },
        {
            "title": "Search guardrails",
            "commands": [
                "archguard search \"managed services\""
                " --severity should --top 5",
            ],
        },
        {
            "title": "Get full detail for a guardrail",
            "commands": [
                "archguard get 01HXYZ...",
            ],
        },
        {
            "title": "Check a proposed decision against the corpus",
            "commands": [posix_check_example],
            "powershell_commands": [powershell_check_example],
        },
        {
            "title": "Update a guardrail (patch semantics)",
            "commands": [posix_update_example],
            "powershell_commands": [powershell_update_example],
        },
        {
            "title": "Add a reference from stdin",
            "commands": [
                "echo '{\"ref_type\":\"adr\",\"ref_id\":\"ADR-001\","
                "\"ref_title\":\"Use managed services\"}'"
                " | archguard ref-add 01HXYZ...",
            ],
            "powershell_commands": [powershell_ref_add_example],
        },
        {
            "title": "Link two guardrails",
            "commands": [
                "archguard link 01HXYZ_FROM 01HXYZ_TO"
                " --rel supports --note 'Both reduce risk'",
            ],
        },
        {
            "title": "Deprecate and supersede",
            "commands": [
                "archguard deprecate 01HXYZ_OLD"
                " --reason 'Replaced by new policy'",
                "archguard supersede 01HXYZ_OLD --by 01HXYZ_NEW",
            ],
        },
        {
            "title": "Review overdue guardrails",
            "commands": [
                "archguard review-due --before 2026-06-01",
            ],
        },
        {
            "title": "Export for Confluence",
            "commands": [
                "archguard export --format markdown --status active",
            ],
        },
        {
            "title": "Bulk import from CSV",
            "commands": [
                "archguard import guardrails.csv",
            ],
        },
        {
            "title": "Detect duplicates",
            "commands": [
                "archguard deduplicate --threshold 0.65",
            ],
        },
    ]


def _compact_task(task: str, data_dir: str) -> dict[str, Any]:
    """Return a task-focused slice of the guide for token-constrained agents."""
    if task == "add-guardrail":
        return {
            "task": "add-guardrail",
            "workflow": _capture_workflow(),
            "provenance_contract": _provenance_contract(),
            "minimum_evidence": _minimum_evidence(),
            "defaulting_policy": _defaulting_policy(),
            "vocabulary": _vocabulary(data_dir),
            "field_semantics": _field_semantics(),
            "quality_criteria": _quality_criteria(),
            "anti_patterns": _anti_patterns(),
            "when_not_to_infer": _when_not_to_infer(),
            "when_not_to_add": _when_not_to_add(),
            "good_and_bad_examples": _good_and_bad_examples(),
            "command": _commands()["add"],
            "hint": "Call 'archguard add --schema' for the exact JSON schema.",
        }
    if task == "check-decision":
        return {
            "task": "check-decision",
            "vocabulary": _vocabulary(data_dir),
            "command": _commands()["check"],
            "hint": "Call 'archguard check --schema' for the exact JSON schema.",
        }
    if task == "add-reference":
        return {
            "task": "add-reference",
            "vocabulary": _vocabulary(data_dir),
            "field_semantics": {
                "references": _field_semantics()["references"],
            },
            "command": _commands()["ref-add"],
        }
    if task == "link-guardrails":
        return {
            "task": "link-guardrails",
            "vocabulary": _vocabulary(data_dir),
            "command": _commands()["link"],
        }
    msg = (
        f"Unknown task '{task}'. "
        f"Available: add-guardrail, check-decision, add-reference, link-guardrails"
    )
    raise ValueError(msg)


@app.command()
def guide(
    pretty: Annotated[
        bool,
        typer.Option(
            "--pretty",
            help="Pretty-print the JSON output for human reading",
        ),
    ] = False,
    task: Annotated[
        str,
        typer.Option(
            "--task",
            help=(
                "Return a compact, task-focused slice of the guide. "
                "Values: add-guardrail, check-decision, add-reference, link-guardrails"
            ),
        ),
    ] = "",
    explain: Annotated[
        bool,
        typer.Option(
            "--explain",
            help="Explain what this command does",
        ),
    ] = False,
) -> None:
    """Return the full CLI schema as JSON.

    Includes commands, flags, error codes, and examples.
    Call once, cache the result.

    Use --task for a compact, task-focused subset (fewer tokens).
    """
    if explain:
        sys.stderr.write(
            "guide returns a machine-readable JSON document describing "
            "every command, flag, error code, exit code, and usage "
            "example. An agent calls this once to bootstrap zero-shot "
            "CLI usage.\n"
            "\n"
            "Use --task to get a compact subset for a specific workflow:\n"
            "  --task add-guardrail    Field contract, vocabulary, examples, anti-patterns\n"
            "  --task check-decision   Check command schema and vocabulary\n"
            "  --task add-reference    Reference types and command schema\n"
            "  --task link-guardrails  Relationship types and command schema\n"
        )
        raise SystemExit(0)

    ensure_supported_format("guide", "json")

    data_dir = state.data_dir

    if task:
        try:
            compact_payload = _compact_task(task, data_dir)
        except ValueError as e:
            handle_error("guide", "ERR_VALIDATION", str(e))
            return
        sys.stdout.write(envelope("guide", compact_payload) + "\n")
        return

    guide_payload = _build_guide(data_dir)
    sys.stdout.write(envelope("guide", guide_payload) + "\n")
