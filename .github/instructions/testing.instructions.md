# Testing Instructions

## Test organization

- `test_models.py` -- Pydantic validation (valid, invalid, edge cases)
- `test_store.py` -- JSONL read/write/rewrite operations
- `test_index.py` -- SQLite schema, build, stale detection
- `test_search.py` -- RRF scoring, ranking
- `test_cli.py` -- CLI integration via `typer.testing.CliRunner`
- `test_properties.py` -- Hypothesis property-based tests

## Fixtures

- `tmp_data_dir` -- Temp directory with empty JSONL files and sample taxonomy
- `sample_guardrail_dict` -- A valid guardrail dict for reuse

## Conventions

- One test class per component/concept
- Use `pytest.raises(ValidationError)` for expected validation failures
- Use `CliRunner.invoke(app, [...])` for CLI tests -- check `exit_code` and `output`
- Hypothesis tests: use `@settings(max_examples=50)` for CI speed

## What to test

- Valid input produces correct output
- Invalid input is rejected with the right error
- Roundtrip: serialize -> deserialize -> compare
- Edge cases: empty files, missing files, duplicate IDs
