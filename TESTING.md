# Testing Strategy

## Test pyramid

1. **Unit tests** (fast, many) -- Pydantic models, JSONL read/write, RRF scoring, cosine similarity
2. **Integration tests** (medium) -- SQLite index build, FTS5 queries, CLI commands via CliRunner
3. **Property-based tests** (Hypothesis) -- Guardrail roundtrip serialization, search invariants

## Running tests

```bash
uv run pytest                    # All tests
uv run pytest -x                 # Stop on first failure
uv run pytest -k test_models     # Specific module
uv run pytest --tb=short         # Shorter tracebacks
```

## Test coverage expectations

- `core/models.py` -- All validation rules, edge cases for every Literal and constraint
- `core/store.py` -- Read/write/rewrite JSONL, empty files, missing files
- `core/index.py` -- Schema creation, stale detection, FTS5 queries
- `core/search.py` -- RRF scoring, ranking correctness
- `core/validator.py` -- Orphan refs, broken links, taxonomy violations
- CLI commands -- Happy path + error cases via `typer.testing.CliRunner`

## What must be tested for each PR

- All existing tests pass (`uv run pytest`)
- New functionality has corresponding tests
- Pydantic model changes have validation tests
- CLI command changes have CliRunner integration tests

## How AI agents should validate changes

1. Run `uv run pytest` and verify all tests pass
2. Run `uv run ruff check src/ tests/` for lint
3. Run `uv run pyright src/` for type checking
4. If modifying models, verify JSON schema output hasn't broken
5. If modifying JSONL operations, run property-based tests: `uv run pytest tests/test_properties.py`
