## Implemented contract (2026-03-07)

- Guardrails now have a persisted secondary user-facing ID in `gr-0001` format.
- Internal ULID `id` values remain the canonical storage and foreign-key identifiers.
- Public IDs are immutable once assigned.
- Public IDs are generated automatically at create/import time using a per-entity guardrail sequence.
- CLI commands that accept a guardrail identifier now accept either the internal ULID or the public ID.
- Human-facing table, markdown, and export surfaces prefer the public ID while JSON payloads still include the internal `id`.

> Note: the detailed plan below reflects an earlier design iteration. Where it conflicts with the bullets above, the implemented contract above is authoritative.

## Plan: Human-readable guardrail IDs

Add a persisted secondary identifier on each guardrail (recommended field name: `human_id`) while keeping the existing ULID `id` as the canonical internal key for storage, links, references, and CLI mutation flows. Generate `human_id` deterministically from an explicit per-operation prefix supplied by the agent/user (for example `TA`) plus a zero-padded sequence (`TA001`, `TA002`, …), backfill existing records in a dedicated maintenance flow, and surface the new identifier in markdown/table/CSV/JSON outputs without changing internal FK semantics.

**Steps**
1. Phase 1 — define the contract and scope. Add a new immutable optional field on `Guardrail` for the human-readable ID; keep ULID `id` unchanged as the only relational key. Extend create/import schemas only where needed so the CLI can receive an explicit prefix for generation, not a precomputed value. This phase blocks all later phases.
2. Phase 1 — document generation rules. Define one regex/validator for the new format (recommended: uppercase letters + zero-padded digits, e.g. `TA001`) and one allocation rule: uniqueness is repository-wide, numbering is per prefix, gaps are allowed, and IDs are never renumbered. This is parallel with step 1 once the field name is chosen.
3. Phase 2 — implement generation helpers in the core/write path. Introduce a shared allocator that scans existing guardrails, finds the max numeric suffix for the requested prefix, and returns the next available `human_id`. Reuse this from `add` and `import`; because the repo usually uses one prefix per repository or backfill batch, keep prefix supply explicit per operation rather than inferred from title. Depends on 1–2.
4. Phase 2 — add a dedicated backfill path for existing records. Implement a maintenance command or sub-flow that assigns missing `human_id` values for a supplied prefix across a selected batch of guardrails, preserving existing values and making the operation idempotent. Because current data does not model corpus membership, scope the first version to a single prefix per repository/backfill batch. Depends on 1–3.
5. Phase 2 — validate corpus integrity. Extend corpus validation to reject duplicate `human_id` values, malformed `human_id` formats, and mixed references to nonexistent human IDs only where applicable; do not change references/links/supersession fields away from ULID storage. Update any helper logic that currently prints `g.id[:8]` warnings so human-facing warnings prefer `human_id` when present. Depends on 1–4.
6. Phase 3 — update read/export/display surfaces. Keep JSON responses backward compatible by continuing to emit `id` and adding `human_id`; update markdown, table, and CSV renderers to prefer `human_id` in human-facing columns and headings, while detail views may optionally show both `human_id` and ULID for traceability. Depends on 1–5.
7. Phase 3 — decide command UX precisely. Add explicit prefix input on create/import/backfill flows (recommended as CLI options, not stdin fields, because the prefix is operation context rather than guardrail content). Do not expand `get`, `update`, `ref-add`, `link`, `related`, `deprecate`, `delete`, or `supersede` to accept human IDs in this iteration. Depends on 1–6.
8. Phase 4 — update index/storage compatibility as needed. If SQLite mirrors all guardrail fields for listing/search/export convenience, add `human_id` there too; otherwise keep it JSONL-only until a query path needs it. Preserve lazy rebuild behavior and backward compatibility for old JSONL lines lacking `human_id` until backfill runs. Depends on 1–7.
9. Phase 4 — test comprehensively. Add model validation tests for accepted/rejected `human_id` values, CLI integration tests for add/import/backfill generation and uniqueness, validator tests for duplicate and malformed human IDs, and export/formatter tests proving markdown/CSV/table prefer `human_id`. Include regression coverage showing ULID-based commands and FK behavior still work unchanged. Depends on 1–8.
10. Phase 4 — update docs and contracts. Revise PRD-facing project docs only where this is now implemented in the codebase, update `CHANGELOG.md`, keep README command tables in sync, and extend `guide`/`--explain` text so agents know when to pass a prefix and that human IDs are for user-facing output while ULIDs remain canonical internally. Depends on 1–9.

**Relevant files**
- `c:\Users\thoma\Projects\archguard\src\archguard\core\models.py` — add `human_id` to `Guardrail`; extend create/import contracts carefully; update `SearchResult` only if human-facing search payload should include it.
- `c:\Users\thoma\Projects\archguard\src\archguard\cli\write.py` — `add`, `update`, `ref-add`, `link`, `delete`, `deprecate`, `supersede`; primary place for generation helper reuse and preserving ULID lookup semantics.
- `c:\Users\thoma\Projects\archguard\src\archguard\cli\maintenance.py` — `import_guardrails()` and the best location for a new backfill/repair command.
- `c:\Users\thoma\Projects\archguard\src\archguard\core\validator.py` — duplicate detection, format validation, and human-facing warning text.
- `c:\Users\thoma\Projects\archguard\src\archguard\core\store.py` — JSONL roundtrip behavior if helpers are needed for scanning or rewriting guardrails.
- `c:\Users\thoma\Projects\archguard\src\archguard\core\index.py` — add mirrored column/index only if read/query paths benefit; keep ULID PK and FK semantics intact.
- `c:\Users\thoma\Projects\archguard\src\archguard\cli\read.py` — no ID lookup broadening in this iteration; only payload enrichment if JSON output should include `human_id`.
- `c:\Users\thoma\Projects\archguard\src\archguard\output\markdown.py` — replace truncated ULID presentation in list/detail/export output with `human_id` preference.
- `c:\Users\thoma\Projects\archguard\src\archguard\output\table.py` — same human-facing preference for tabular output.
- `c:\Users\thoma\Projects\archguard\src\archguard\cli\export.py` — add `human_id` to CSV/full export behavior where appropriate.
- `c:\Users\thoma\Projects\archguard\src\archguard\output\json.py` — ensure JSON envelopes remain backward compatible while including `human_id` in payloads.
- `c:\Users\thoma\Projects\archguard\tests\test_models.py` — new field validation coverage.
- `c:\Users\thoma\Projects\archguard\tests\test_cli.py` — add/create/import/backfill UX and backward-compat integration tests.
- `c:\Users\thoma\Projects\archguard\tests\test_validator.py` — duplicate/malformed human ID corpus checks.
- `c:\Users\thoma\Projects\archguard\tests\test_export.py` — markdown/CSV/JSON export assertions.
- `c:\Users\thoma\Projects\archguard\tests\test_store.py` — roundtrip persistence with and without `human_id`.
- `c:\Users\thoma\Projects\archguard\CHANGELOG.md` — user-visible change note.
- `c:\Users\thoma\Projects\archguard\README.md` — command table and authoring guidance.
- `c:\Users\thoma\Projects\archguard\PRD.md` — update only if the implementation is accepted as a new contract, because the current PRD still states ULID as the single `id`.

**Verification**
1. Run CLI integration tests covering create/import/backfill flows and confirm generated `human_id` values are unique, monotonic per prefix, and preserved on update.
2. Run validator tests proving duplicate and malformed `human_id` values fail with the expected validation/integrity errors.
3. Run export/formatter tests proving markdown, CSV, and table output prefer `human_id` while JSON still includes canonical ULIDs.
4. Run the full validation suite used by the repo: `uv run pytest`, `uv run ruff check src/ tests/`, and `uv run pyright src/`.
5. Perform a manual smoke check on a sample corpus: add two guardrails with prefix `TA`, backfill an old corpus with the same prefix, then export markdown and confirm `TA001`/`TA002` style IDs appear consistently without breaking ULID-based commands.

**Decisions**
- Keep ULID `id` as the sole canonical internal identifier; `human_id` is a persisted secondary identifier for human-facing output.
- Prefix is supplied explicitly by the agent/user per add/import/backfill operation; it is not auto-derived from titles.
- CLI lookup stays ULID-based in this iteration; accepting both ULID and `human_id` is deliberately excluded to keep scope and ambiguity down.
- Existing records should be backfilled, but the first version assumes a single prefix per repository or backfill batch because corpus membership is not modeled today.
- Repository-wide uniqueness applies to `human_id`; numbering is per prefix, gaps are acceptable, and values are immutable once assigned.

**Further Considerations**
1. If mixed corpora per repository become common, add an explicit `source_corpus`/`corpus_prefix` field later instead of overloading `metadata`; that would enable safe multi-prefix backfill and filtering.
2. Decide whether markdown detail views should show both `human_id` and ULID (recommended for traceability) or only `human_id` (cleaner for readers).
3. If search/list consumers begin to rely on `human_id`, mirror it into SQLite with an index in the same change; otherwise defer that part to reduce migration scope.