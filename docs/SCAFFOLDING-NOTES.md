# Scaffolding Notes

## What was inferred from the PRD

- **Project type:** Python CLI tool distributed via `uv tool install`
- **Stack:** Fully specified in PRD Section 15 -- no inference needed
- **Structure:** Specified in PRD Section 16 -- followed exactly
- **Data model:** Specified in PRD Section 5 -- implemented as Pydantic models
- **Command surface:** Specified in PRD Section 9 -- all commands stubbed
- **Exit codes:** Specified in PRD Section 12 -- error handling scaffolded
- **Search architecture:** Specified in PRD Section 10 -- RRF scoring implemented

## What was scaffolded

### Source code
- All CLI commands (5 modules: setup, write, read, export, maintenance)
- Core business logic (6 modules: models, store, index, search, embeddings, validator)
- Output formatting (3 modules: json, table, markdown)
- Entry point with global options (format, quiet, data-dir)

### Tests
- 6 test modules covering models, store, index, search, CLI, and property-based tests
- Shared fixtures in conftest.py
- Working tests for: Pydantic validation, JSONL read/write, SQLite schema, RRF scoring, init command

### Functional code (not just stubs)
- `init` command -- creates data directory, JSONL files, taxonomy, .gitignore
- Pydantic models -- full validation for all domain objects
- JSONL store -- read, append, rewrite operations
- SQLite schema -- tables, FTS5, pragmas
- RRF scoring -- cosine similarity, embedding conversion
- Validator -- FK integrity checks, taxonomy validation

### Documentation
- README, PROJECT, ARCHITECTURE, TESTING, CONTRIBUTING, SECURITY, CHANGELOG
- AGENTS.md, copilot-instructions.md, path-specific instructions
- ADR-0001, DOMAIN.md, GLOSSARY.md, ROADMAP.md
- PR template, CI workflow

## What still needs human input

1. **Model2Vec download in `init`** -- The model download/bundling logic needs implementation. Currently creates empty directory structure.
   TODO: Implement model download from HuggingFace and bundling under `guardrails/models/`.

2. **Full SQLite build pipeline** -- Schema is defined, but INSERT/FTS5 population/embedding storage is stubbed.
   TODO: Wire up `build_index()` in `core/index.py` with actual data insertion.

3. **All write commands beyond `init`** -- `add`, `update`, `ref-add`, `link`, `deprecate`, `supersede` are stubbed.
   TODO: Implement following the mutation pattern in ARCHITECTURE.md.

4. **All read commands** -- `search`, `get`, `related`, `list`, `check` are stubbed.
   TODO: Implement queries against SQLite index with lazy auto-build.

5. **Rich table output** -- `output/table.py` is a placeholder.
   TODO: Implement Rich table formatting for `--format table`.

6. **Markdown export** -- `output/markdown.py` is a placeholder.
   TODO: Implement Confluence-ready markdown per PRD Section 13.3.

7. **Security contact** -- SECURITY.md has a TODO for vulnerability reporting process.

## Highest-risk ambiguities

None significant -- the PRD is unusually thorough. All architectural decisions are resolved (PRD Section 20). The main implementation risk is ensuring FTS5 and Model2Vec produce good enough search quality for the guardrails domain.
