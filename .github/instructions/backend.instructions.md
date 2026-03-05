# Backend Instructions

## Core layer (`src/guardrails_cli/core/`)

- `models.py` -- All Pydantic models. Add new fields here first, then update store/index.
- `store.py` -- JSONL read/write. Uses rewrite-on-edit semantics for mutations.
- `index.py` -- SQLite schema and build. Must match the fields in models.py.
- `search.py` -- Hybrid search with RRF. BM25 via FTS5, vector via Model2Vec.
- `embeddings.py` -- Model2Vec wrapper. Concatenates `title + guidance + rationale` for embedding.
- `validator.py` -- Integrity checks (FK integrity, taxonomy, duplicates).

## Mutation pattern

Every write operation follows:
1. Validate input (Pydantic)
2. Write to JSONL (source of truth)
3. Rebuild SQLite index
4. Return result as JSON on stdout

## SQLite conventions

- Always use parameterized queries
- Use `get_connection()` from `index.py` for consistent pragmas
- FTS5 uses `unicode61 remove_diacritics 2` tokenizer
- Embeddings stored as float32 BLOBs

## Error handling

- Use exit codes from PRD Section 12
- Use `handle_error()` from `cli/__init__.py`
- Never print unstructured text to stdout
