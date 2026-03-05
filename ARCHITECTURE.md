# Architecture: guardrails-cli

## Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Runtime | Python 3.12+ | Broad ecosystem, native `tomllib` |
| Package Manager | uv 0.5+ | Fast, reproducible, `uv tool install` |
| CLI Framework | Typer 0.12+ | Rich integration, type-safe |
| Validation | Pydantic v2 | Fast (Rust core), JSON Schema generation |
| Database | SQLite 3.45+ | WAL mode, FTS5, zero setup |
| Embeddings | Model2Vec (potion-base-8M) | numpy-only, static, deterministic, ~8 MB |
| Human Output | Rich 13.0+ | Tables, panels, progress bars |
| JSON | orjson 3.9+ | Fast serialization |
| IDs | python-ulid | Sortable, timestamp-embedded |

Stack is specified by the PRD. No provisional choices.

## Major components

```
CLI Layer (Typer)          -- Command parsing, global options, --explain/--schema
    |
Core Layer                 -- Business logic, validation, search
    ├── models.py          -- Pydantic data models (domain + I/O contracts)
    ├── store.py           -- JSONL persistence (source of truth)
    ├── index.py           -- SQLite index (derived, gitignored)
    ├── search.py          -- Hybrid BM25 + vector + RRF
    ├── embeddings.py      -- Model2Vec wrapper
    └── validator.py       -- Integrity checks
    |
Output Layer               -- Format dispatch (JSON, Rich table, Markdown)
```

## Key design decisions

### JSONL is source, SQLite is index

- JSONL files are committed to Git (source of truth)
- SQLite is a derived runtime artifact (gitignored, rebuilt from JSONL)
- Lazy auto-build: read commands check mtime, rebuild if stale

### Edit semantics: rewrite-on-edit

Mutations read all lines, find matching ID, replace that line, write the whole file back. Simple, correct, performant at this scale.

### Hybrid search with RRF

Two retrieval methods merged via Reciprocal Rank Fusion:
- BM25 via FTS5 (exact terminology)
- Cosine similarity via Model2Vec (semantic matches)
- `RRF_score(d) = sum(1 / (k + rank_i(d)))`, k=60

### No delete, only deprecate/supersede

Governance audit trail matters. Git history provides versioning.

## Data flow

```
Agent stdin (JSON) -> Pydantic validation -> JSONL append/rewrite -> SQLite rebuild -> JSON stdout
```

## Architectural constraints

- No LLM inference in the CLI
- All commands produce structured JSON on stdout by default
- Exit codes are stable (see PRD S12)
- Stdin for write input (no shell escaping issues)

## Quality attributes

- **Determinism**: Same input always produces same output
- **Performance**: build <5s for 500 guardrails, search <200ms, startup <200ms
- **Portability**: No external services required after init

## Trade-offs

- Rewrite-on-edit is O(n) but simple; fine for <10K guardrails
- Brute-force cosine is O(n) but sub-ms at scale; no ANN index needed
- Bundling 8 MB model in Git is unusual but ensures reproducibility
