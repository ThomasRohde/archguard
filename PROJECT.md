# Project: guardrails-cli

## Problem statement

Architecture guardrails are scattered across Confluence, Word, PowerPoint, and tribal knowledge. There is no queryable, authoritative source for AI agents or human architects.

## Target users

- AI agents performing governance consultation or architectural validation
- Enterprise architects managing standards and constraints
- Platform teams enforcing architectural guardrails in CI/CD

## Goals

1. Single, queryable store of architecture guardrails (BM25 + vector search)
2. AI agent ingestion from source documents with deduplication
3. Governance consultation: "what guardrails apply?"
4. Structured validation: check decisions against the corpus
5. Git-friendly JSONL storage (reviewable, diffable, mergeable)
6. Agent-friendly CLI (JSON output, stable exit codes, progressive discoverability)

## Non-goals

- No LLM inference inside the CLI (deterministic tool)
- No cloud sync, API server, or multi-machine replication
- No GUI
- No automatic conflict resolution
- No delete command (deprecate/supersede only)

## Scope boundaries

- English only (FTS5 `unicode61` tokenizer)
- Hundreds to low thousands of guardrails (brute-force cosine is fine)
- Single-machine, single-user at a time (SQLite WAL for concurrent reads)

## Constraints

- Python 3.12+, installable via `uv tool install`
- Embedding model bundled in repo (~8 MB)
- All output defaults to JSON on stdout
- Exit codes are stable and documented

## Assumptions

- Users have `uv` installed
- The guardrails corpus fits comfortably in memory
- Git is the collaboration and audit mechanism

## Success criteria

- See PRD.md Section 18 (Acceptance Criteria)

## Open questions

- See PRD.md Section 20 (all currently resolved)
