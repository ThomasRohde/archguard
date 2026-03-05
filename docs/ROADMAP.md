# Roadmap

Based on PRD Section 19 (MVP Milestones). Items marked **[confirmed]** are from the PRD; items marked **[inferred]** are reasonable additions.

## M1: Core Store

- [confirmed] `init`, `build`, `validate` commands
- [confirmed] `add`, `get`, `list` commands
- [confirmed] JSONL read/write with Pydantic validation
- [confirmed] SQLite index build with FTS5
- [confirmed] JSON output formatting

**Key deliverable:** A working pipeline from `init` -> `add` -> `get` -> `list`.

## M2: Search and Retrieval

- [confirmed] `search` with BM25 (FTS5)
- [confirmed] Model2Vec integration and vector search
- [confirmed] Hybrid RRF fusion
- [confirmed] `check` command

**Key deliverable:** Hybrid search returns relevant guardrails for a query.

## M3: Relationships and Lifecycle

- [confirmed] `update` (patch semantics), `ref-add`, `link`
- [confirmed] `related`, `deprecate`, `supersede`
- [confirmed] `review-due`, `stats`

**Key deliverable:** Full lifecycle management and relationship graph.

## M4: Export, Import, Polish

- [confirmed] `export` (JSON, CSV, Markdown)
- [confirmed] `import` (bulk upsert)
- [confirmed] `deduplicate`
- [confirmed] CI/CD examples
- [confirmed] Documentation and README

**Key deliverable:** Production-ready tool with publishing pipeline support.

## Risks and dependencies

- Model2Vec model download during `init` requires network access (one-time)
- FTS5 availability depends on SQLite build flags (standard on most systems)
- Hypothesis tests may surface edge cases in Pydantic validation that need decisions
