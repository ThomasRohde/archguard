# Copilot Instructions: guardrails-cli

## Repo-wide guidance

- This is a Python 3.12+ CLI tool using Typer, Pydantic v2, SQLite, and Model2Vec
- Read `PRD.md` before making architectural decisions -- it is the source of truth
- Read `AGENTS.md` for coding rules and invariants

## Naming conventions

- Snake case for all Python identifiers
- CLI commands use kebab-case (e.g., `ref-add`, `review-due`)
- Pydantic models use PascalCase
- Constants in UPPER_SNAKE_CASE

## Preferred patterns

- Use Pydantic for all data validation (never manual dict checking)
- Use orjson for JSON (never stdlib json)
- Use `from __future__ import annotations` in all modules
- Use `typer.Option` / `typer.Argument` with type annotations for CLI args
- Follow the success/error envelope pattern for JSON output
- Use `handle_error()` from `cli/__init__.py` for error exits

## Testing expectations

- Every new command needs a CliRunner integration test
- Every new model field needs a validation test
- Use pytest fixtures from `conftest.py`
- Use Hypothesis for roundtrip/invariant properties

## Documentation expectations

- Update CHANGELOG.md for user-visible changes
- New commands must have `--explain` flag support
- Keep README.md command table in sync
