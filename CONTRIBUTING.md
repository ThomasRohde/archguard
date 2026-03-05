# Contributing to guardrails-cli

## Setup

```bash
uv sync                          # Install all dependencies including dev
uv run pytest                    # Verify tests pass
```

## Branch and PR workflow

1. Create a feature branch from `main`
2. Make changes, add tests
3. Run `uv run pytest && uv run ruff check src/ tests/ && uv run pyright src/`
4. Commit with a clear message describing the "why"
5. Open a PR against `main`

## Code style

- Formatting and linting: `ruff` (configured in pyproject.toml)
- Type checking: `pyright` in strict mode
- Follow existing patterns in `src/guardrails_cli/`
- No docstrings on obvious methods; add comments only where logic isn't self-evident

## Commit expectations

- One logical change per commit
- Prefix with area: `core: add JSONL rewrite`, `cli: implement search command`, `tests: add FTS5 query tests`

## Review checklist

- [ ] Tests pass (`uv run pytest`)
- [ ] Lint clean (`uv run ruff check src/ tests/`)
- [ ] Types clean (`uv run pyright src/`)
- [ ] New commands have `--explain` and `--help` text
- [ ] Exit codes follow PRD Section 12
- [ ] JSON output follows established envelope format (`{"ok": true, ...}`)

## Architectural changes

For changes to data models, storage format, or search architecture, update `ARCHITECTURE.md` and reference the relevant PRD section.
