# Architecture Guardrails

## Summary

| Metric | Count |
| --- | --- |
| Status: active | 7 |
| Severity: must | 6 |
| Severity: should | 1 |
| **Total** | **7** |

## cli-contract

### **[MUST]** Emit structured JSON on stdout and reserve stderr for diagnostics

**Public ID:** `gr-0003`

**Internal ID:** `01KK3HVXAAZJADJD6TC5GDEY2V`

**Scope:** cli-contract

**Status:** active | **Owner:** EA Team

**Guidance:**

Emit structured JSON on stdout for command results and errors. Write progress and diagnostics to stderr, and keep command responses aligned with the published envelope and exit-code contract.

**Rationale:**

Agent automation depends on a stable response envelope and predictable separation of machine-readable output from human diagnostics.

**References:**

- [document] AGENTS.md Coding rules - [AGENTS.md](AGENTS.md)
  > stdout: structured JSON only (default). stderr: diagnostics.
- [document] CLI-MANIFEST.md Part I Foundations - [CLI-MANIFEST.md#1-every-command-returns-a-structured-envelope](CLI-MANIFEST.md#1-every-command-returns-a-structured-envelope)
  > Every command - success or failure - returns the same top-level JSON shape.

**Links:**

- <- supports `gr-0001` - Keep JSONL as the source of truth and rebuild SQLite as derived state (Derived indexing and maintenance flows depend on stable machine-readable command output.)
- <- supports `gr-0002` - Keep the CLI deterministic and free of LLM inference (Deterministic runtime behavior reinforces the structured CLI contract.)
- <- implements `gr-0004` - Validate data with Pydantic and serialize JSON with orjson (Pydantic validation and orjson serialization make the published envelope concrete.)
- <- supports `gr-0005` - Read write-command payloads from stdin and expose explainable contracts (Explainable stdin-driven workflows complement machine-readable command responses.)

### **[MUST]** Read write-command payloads from stdin and expose explainable contracts

**Public ID:** `gr-0005`

**Internal ID:** `01KK3HVZ4JF1K7BMMAEEABBK30`

**Scope:** cli-contract, agent-experience

**Status:** active | **Owner:** EA Team

**Guidance:**

Use stdin for all write-command JSON payloads. Support --explain on all commands. Provide --schema on add and check so agents can bootstrap usage from the CLI itself.

**Rationale:**

Agents need stable input channels and discoverable contracts so they can compose requests without shell-escaping games or external documentation.

**References:**

- [document] AGENTS.md Coding rules - [AGENTS.md](AGENTS.md)
  > All write commands read JSON from stdin
- [document] AGENTS.md Coding rules - [AGENTS.md](AGENTS.md)
  > All commands support --explain; add and check support --schema

**Links:**

- supports -> `gr-0003` - Emit structured JSON on stdout and reserve stderr for diagnostics (Explainable stdin-driven workflows complement machine-readable command responses.)

## data-model

### **[MUST]** Validate data with Pydantic and serialize JSON with orjson

**Public ID:** `gr-0004`

**Internal ID:** `01KK3HVY86ER0Z6KR92C1DE936`

**Scope:** data-model

**Status:** active | **Owner:** EA Team

**Guidance:**

Use Pydantic v2 for all data validation and use orjson for JSON serialization. Avoid ad hoc dict validation and avoid falling back to the standard json module in core CLI flows.

**Rationale:**

The project standardizes validation and serialization choices so schemas, performance, and behavior stay consistent across the CLI.

**References:**

- [document] AGENTS.md Coding rules - [AGENTS.md](AGENTS.md)
  > Use Pydantic v2 for all data validation
- [document] AGENTS.md Coding rules - [AGENTS.md](AGENTS.md)
  > Use orjson for JSON serialization (not stdlib json)

**Links:**

- implements -> `gr-0003` - Emit structured JSON on stdout and reserve stderr for diagnostics (Pydantic validation and orjson serialization make the published envelope concrete.)
- <- requires `gr-0007` - Gate changes with tests, lint, and type checking (Quality gates must exercise the shared validation and serialization contract.)

## lifecycle-governance

### **[SHOULD]** Prefer deprecate or supersede workflows over destructive deletion

**Public ID:** `gr-0006`

**Internal ID:** `01KK3HW00MG897MYYZ43G2RTCA`

**Scope:** lifecycle-governance

**Status:** active | **Owner:** EA Team

**Guidance:**

Prefer deprecate or supersede workflows when replacing or retiring a guardrail. Use delete only for exceptional cleanup scenarios and require explicit confirmation before destructive removal.

**Rationale:**

Governance records benefit from an audit trail, so retirement should usually preserve history rather than erase it.

**Exceptions:**

Deletion is reserved for deliberate repository cleanup with explicit confirmation and documented intent.

**References:**

- [document] AGENTS.md Architectural invariants - [AGENTS.md](AGENTS.md)
  > Prefer deprecate/supersede over delete; delete exists but requires --confirm
- [document] PRD.md Non-Goals - [PRD.md#3-non-goals](PRD.md#3-non-goals)
  > Guardrails are deprecated or superseded, never deleted. The governance audit trail matters.

**Links:**

- supports -> `gr-0001` - Keep JSONL as the source of truth and rebuild SQLite as derived state (Preserving history complements the repository source-of-truth model.)

## quality-gates

### **[MUST]** Gate changes with tests, lint, and type checking

**Public ID:** `gr-0007`

**Internal ID:** `01KK3HW0V0GD5T1BC8XE334NXT`

**Scope:** quality-gates

**Status:** active | **Owner:** EA Team

**Guidance:**

Run pytest, Ruff, and Pyright for every pull request. Add corresponding tests for new functionality and validate model or JSONL changes with the appropriate focused coverage.

**Rationale:**

The project relies on automated validation to keep CLI behavior, schemas, and implementation quality aligned as the codebase evolves.

**References:**

- [document] TESTING.md What must be tested for each PR - [TESTING.md](TESTING.md)
  > All existing tests pass (uv run pytest)
- [document] AGENTS.md How to run validation - [AGENTS.md](AGENTS.md)
  > uv run pytest; uv run ruff check src/ tests/; uv run pyright src/

**Links:**

- requires -> `gr-0004` - Validate data with Pydantic and serialize JSON with orjson (Quality gates must exercise the shared validation and serialization contract.)

## runtime-architecture

### **[MUST]** Keep the CLI deterministic and free of LLM inference

**Public ID:** `gr-0002`

**Internal ID:** `01KK3HVWDHH0JQ88CH4HY5FSQT`

**Scope:** runtime-architecture, agent-experience

**Status:** active | **Owner:** EA Team

**Guidance:**

Do not implement LLM inference inside the CLI. Keep behavior deterministic so the same input produces the same output and agents provide reasoning outside the tool.

**Rationale:**

The tool is designed as a deterministic governance system whose behavior must not depend on model calls at runtime.

**References:**

- [document] PRD.md Non-Goals - [PRD.md#3-non-goals](PRD.md#3-non-goals)
  > No LLM inference inside the CLI. The tool is deterministic. The agent provides the intelligence.
- [document] AGENTS.md Architectural invariants - [AGENTS.md](AGENTS.md)
  > No LLM inference inside the CLI

**Links:**

- supports -> `gr-0003` - Emit structured JSON on stdout and reserve stderr for diagnostics (Deterministic runtime behavior reinforces the structured CLI contract.)

## storage-architecture

### **[MUST]** Keep JSONL as the source of truth and rebuild SQLite as derived state

**Public ID:** `gr-0001`

**Internal ID:** `01KK3HVVFK7XRC6WVDZ2B258TM`

**Scope:** storage-architecture

**Status:** active | **Owner:** EA Team

**Guidance:**

Keep authoritative corpus data in JSONL files only. Treat SQLite as a derived artifact, rebuild it from JSONL after writes, and never make SQLite-only changes the source of record.

**Rationale:**

The repository depends on reviewable JSONL data and a rebuildable SQLite index to preserve Git-friendly diffs and deterministic rebuilds.

**References:**

- [document] PRD.md Section 6.1 Design Principle: JSONL is Source, SQLite is Index - [PRD.md#61-design-principle-jsonl-is-source-sqlite-is-index](PRD.md#61-design-principle-jsonl-is-source-sqlite-is-index)
  > JSONL files are the source of truth. SQLite is a derived runtime artifact.
- [document] AGENTS.md Architectural invariants - [AGENTS.md](AGENTS.md)
  > JSONL files are the source of truth; SQLite is derived

**Links:**

- supports -> `gr-0003` - Emit structured JSON on stdout and reserve stderr for diagnostics (Derived indexing and maintenance flows depend on stable machine-readable command output.)
- <- supports `gr-0006` - Prefer deprecate or supersede workflows over destructive deletion (Preserving history complements the repository source-of-truth model.)


