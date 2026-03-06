"""Guide command: machine-readable CLI schema in one call (CLI-MANIFEST §4)."""

from __future__ import annotations

import sys
from typing import Annotated, Any

import typer

from archguard.cli import app
from archguard.output.json import (
    ERROR_EXIT_MAP,
    SCHEMA_VERSION,
    envelope,
)


def _build_guide() -> dict[str, Any]:
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
        "global_options": {
            "--format, -f": {
                "type": "string",
                "values": ["json", "table", "markdown"],
                "default": "json",
                "description": (
                    "Output format. json wraps in structured envelope; "
                    "table/markdown are human-readable."
                ),
            },
            "--quiet, -q": {
                "type": "bool",
                "default": False,
                "description": "Suppress stderr progress messages.",
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
            "10": (
                "Validation error "
                "(bad input, schema mismatch, resource not found)"
            ),
            "40": "Conflict (stale state, already exists, invalid transition)",
            "50": "I/O error (file not found, disk full)",
            "90": "Internal error (bug)",
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
    }


def _commands() -> dict[str, Any]:
    """Command catalog grouped by read/write/maintenance."""
    return {
        "init": {
            "group": "setup",
            "mutates": True,
            "description": (
                "Create guardrails data directory, JSONL files, "
                "taxonomy, and .gitignore."
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
                "ranked by RRF."
            ),
            "args": ["QUERY"],
            "flags": [
                "--status", "--severity", "--scope", "--applies-to",
                "--lifecycle-stage", "--owner", "--top N", "--explain",
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
                "corpus. Reads context JSON from stdin."
            ),
            "args": [],
            "flags": ["--explain", "--schema"],
            "stdin": {
                "format": "JSON",
                "required_fields": ["decision"],
                "optional_fields": [
                    "scope[]", "applies_to[]",
                    "lifecycle_stage", "tags[]",
                ],
            },
            "result_fields": ["context", "matches[]", "summary"],
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
            "flags": ["--rel TYPE", "--note TEXT", "--explain"],
            "stdin": None,
            "result_fields": ["link"],
        },
        "delete": {
            "group": "write",
            "mutates": True,
            "description": (
                "Permanently delete a guardrail and its "
                "associated references and links."
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
                "hybrid FTS + vector similarity."
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
                "Bulk upsert guardrails from a JSON or CSV file."
            ),
            "args": ["FILE"],
            "flags": ["--explain"],
            "stdin": None,
            "result_fields": ["imported", "updated", "errors[]"],
        },
        "export": {
            "group": "maintenance",
            "mutates": False,
            "description": (
                "Export guardrails in JSON, CSV, or Markdown format."
            ),
            "args": [],
            "flags": [
                "--format TYPE", "--status", "--severity",
                "--scope", "--explain",
            ],
            "stdin": None,
            "result_fields": ["guardrails[]"],
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
    add_example = (
        "echo '{\"title\":\"Prefer managed services\","
        "\"severity\":\"should\","
        "\"rationale\":\"Reduce ops burden\","
        "\"guidance\":\"Use managed offerings\","
        "\"scope\":[\"it-platform\"],"
        "\"applies_to\":[\"technology\"],"
        "\"owner\":\"Platform Team\"}' | archguard add"
    )
    check_example = (
        "echo '{\"decision\":\"Use self-hosted Kafka\","
        "\"scope\":[\"it-platform\"],"
        "\"tags\":[\"kafka\"]}' | archguard check"
    )
    update_example = (
        "echo '{\"severity\":\"must\","
        "\"guidance\":\"Updated guidance\"}'"
        " | archguard update 01HXYZ..."
    )
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
            "commands": [add_example],
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
            "commands": [check_example],
        },
        {
            "title": "Update a guardrail (patch semantics)",
            "commands": [update_example],
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
                "archguard deduplicate --threshold 0.8",
            ],
        },
    ]


@app.command()
def guide(
    pretty: Annotated[
        bool,
        typer.Option(
            "--pretty",
            help="Pretty-print the JSON output for human reading",
        ),
    ] = False,
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
    """
    if explain:
        sys.stdout.write(
            "guide returns a machine-readable JSON document describing "
            "every command, flag, error code, exit code, and usage "
            "example. An agent calls this once to bootstrap zero-shot "
            "CLI usage.\n"
        )
        raise SystemExit(0)

    guide_payload = _build_guide()

    if pretty:
        import orjson

        raw = envelope("guide", guide_payload)
        parsed = orjson.loads(raw)
        sys.stdout.write(
            orjson.dumps(parsed, option=orjson.OPT_INDENT_2).decode()
            + "\n"
        )
    else:
        sys.stdout.write(envelope("guide", guide_payload) + "\n")
