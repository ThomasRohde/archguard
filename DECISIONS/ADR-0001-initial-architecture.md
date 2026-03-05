# ADR-0001: Initial Architecture

**Status:** Accepted
**Date:** 2026-03-05
**Context:** Scaffolding the guardrails-cli project from PRD.md

## Decision

Adopt the architecture specified in PRD.md Sections 5-7 and 15-16:

- **JSONL as source of truth**, SQLite as derived index (gitignored)
- **Python 3.12+ with uv** for packaging and installation
- **Typer** for CLI framework with Rich for human output
- **Pydantic v2** for all data validation
- **SQLite FTS5** for full-text search
- **Model2Vec (potion-base-8M)** for semantic embeddings (~8 MB, bundled in repo)
- **Reciprocal Rank Fusion (RRF)** for merging BM25 + vector search results

## Rationale

All choices are specified in the PRD based on the team's constraints:
- Must be installable via `uv tool install`
- Must work offline after initial setup
- Must produce Git-friendly diffs (JSONL, not SQLite)
- Must be deterministic (no LLM inference)
- Must be fast (sub-200ms search at 500 guardrails)

## Consequences

- SQLite must be rebuilt from JSONL on every mutation (acceptable at <10K records)
- Embedding model adds ~8 MB to the Git repository
- No cloud/API capability -- single-machine tool only

## What remains provisional

Nothing -- all architectural decisions are specified in the PRD.
