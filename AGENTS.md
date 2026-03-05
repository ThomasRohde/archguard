# Agent Instructions: guardrails-cli

## Project overview

This is a Python CLI tool (`guardrails-cli`) for managing architecture guardrails. It provides a queryable store backed by JSONL files (source of truth) and a SQLite index (derived artifact) with hybrid BM25 + vector search.

## Where to look first

1. `PRD.md` -- The authoritative requirements document. All design decisions trace back here.
2. `src/guardrails_cli/core/models.py` -- Pydantic data models define the domain.
3. `src/guardrails_cli/core/store.py` -- JSONL persistence layer.
4. `src/guardrails_cli/cli/` -- Command definitions (one file per command group).

## Authoritative files

- `PRD.md` -- Requirements and design decisions
- `CLI-MANIFEST.md` -- CLI contract (output format, exit codes, discoverability)
- `src/guardrails_cli/core/models.py` -- Data model definitions
- `pyproject.toml` -- Dependencies and tool configuration

## Coding rules

- Python 3.12+, type hints required
- Use Pydantic v2 for all data validation
- Use orjson for JSON serialization (not stdlib json)
- Use python-ulid for ID generation
- stdout: structured JSON only (default). stderr: diagnostics.
- Exit codes must match PRD Section 12 exactly
- All write commands read JSON from stdin
- All read commands support `--explain` and `--schema` flags

## Architectural invariants (do not change casually)

- JSONL files are the source of truth; SQLite is derived
- No LLM inference inside the CLI
- No delete command (deprecate/supersede only)
- Rewrite-on-edit for JSONL mutations
- Lazy auto-build: check mtime before queries
- Error responses use the `{"ok": false, "error": {...}}` envelope

## How to run validation

```bash
uv run pytest                          # All tests
uv run ruff check src/ tests/         # Lint
uv run pyright src/                    # Type check
```

## How to handle ambiguity

- If the PRD doesn't specify behavior, leave a `TODO:` with a clear description of what needs deciding.
- Do not invent guardrail-level design decisions.
- When in doubt, follow existing patterns in the codebase.

## When to stop and leave a TODO

- Unclear requirements that need human input
- Design decisions not covered by the PRD
- Integration points with external systems (Model2Vec download, publishing pipelines)

## Expected output style

- Code: Clean, minimal, follows existing patterns. No over-engineering.
- Tests: One test class per component, clear arrange/act/assert.
- Commits: `area: description` format.
- PRs: Short title, bulleted summary, test plan.
