# Archguard CLI v0.5.0 — Blackbox Test Feedback

**Date:** 2026-03-06
**Tester:** Claude (automated blackbox test)
**Platform:** Windows 11, Python 3.13

---

## Summary

Archguard is a well-designed, deterministic CLI for managing architecture guardrails with hybrid BM25 + vector search. It is clearly built with AI agent consumption in mind and succeeds at that goal. The structured JSON envelope, consistent error codes, `--schema`/`--explain` flags, and `LLM=true` environment variable all demonstrate thoughtful design for machine-readable interaction.

Overall impression: **very polished for a v0.5.0 release**. A few issues found, mostly around export/import roundtrip and minor UX papercuts.

---

## What Works Well

### Structured Output Envelope
Every command returns a consistent JSON envelope with `ok`, `errors`, `warnings`, `metrics`, and `request_id`. This is excellent for programmatic consumption. Error responses include actionable `code`, `suggested_action`, and `retryable` fields — better than most production CLIs.

### Multiple Output Formats
`--format json|table|markdown` works across commands. Table output is well-formatted with Rich. Markdown export is particularly impressive — it groups guardrails by scope, includes references, and renders a full document suitable for Confluence or similar.

### Taxonomy Validation
Scope values are validated against `taxonomy.json` at add-time. The error message helpfully lists all allowed values, which is ideal for agent self-correction.

### Hybrid Search
BM25 + vector search with RRF ranking works correctly. The `match_sources` field in results (showing `["bm25"]`, `["vector"]`, or `["bm25","vector"]`) provides good transparency into how results were ranked.

### Lifecycle Management
The `deprecate` and `supersede` workflows enforce valid state transitions (e.g., cannot supersede a deprecated guardrail — must be draft or active). The `superseded_by` field and automatic link creation on supersede are well-thought-out.

### Agent Bootstrap (`guide` command)
The `guide` command returns a comprehensive machine-readable schema of the entire CLI — commands, flags, stdin formats, error codes, concurrency rules, and examples. This is an excellent pattern for LLM tool-use bootstrapping.

### `--schema` and `--explain` Flags
- `--schema` on `add` and `check` returns the JSON Schema for stdin input — perfect for agents to self-validate before calling.
- `--explain` outputs a human-readable description of what the command does, written to stderr so it doesn't pollute machine-readable stdout.

### Init Idempotency
Running `init` on an already-initialized directory succeeds with a warning ("Data directory already exists; existing data preserved") rather than failing or overwriting. Good safety.

### Duplicate Title Detection
Adding a guardrail with an existing title returns `ERR_CONFLICT_EXISTS` with a clear message. Prevents accidental duplicates.

---

## Bugs

### BUG-1: CSV Export Missing Critical Columns (Severity: High)

**Reproduce:**
```bash
archguard export --format csv -q > export.csv
archguard import export.csv -q
```

**Expected:** CSV export/import roundtrip should work.

**Actual:** CSV export header is:
```
id,title,status,severity,scope,applies_to,owner,review_date,created_at,updated_at
```
Missing `rationale` and `guidance` — both required fields for import. Import fails with validation errors for every record:
```
"Record 0: 2 validation errors for GuardrailCreate\nrationale\n  Field required..."
```

The CSV export is not roundtrip-compatible. Either:
1. Include `rationale` and `guidance` in the CSV export, or
2. Make import more lenient for upserts (existing records shouldn't need all required fields)

JSON export/import roundtrip works correctly (0 imported, 4 updated).

### BUG-2: Search Returns All Results for Unrelated Queries (Severity: Low)

**Reproduce:**
```bash
archguard search "completely unrelated quantum physics" -q
```

**Expected:** No results or very low-scoring results below a threshold.

**Actual:** Returns all 4 guardrails with scores between 0.015–0.016 (all via `["vector"]` only). There is no minimum relevance threshold, so vector search always returns results even for semantically unrelated queries. This could mislead agents into thinking there are relevant guardrails when none exist.

**Suggestion:** Consider a `--min-score` flag or a default minimum relevance cutoff, at least when no BM25 matches are found.

---

## Suggestions

### SUG-1: Exit Code Not Propagated on Some Errors

When `add` fails with `ERR_CONFLICT_EXISTS` or `ERR_VALIDATION_JSON`, the exit code appears to be inconsistently reported (the `$?` after the command shows blank in some cases, though the JSON response clearly indicates an error). This could be a shell/pipe artifact, but worth verifying exit codes are always set correctly.

### SUG-2: `--explain` Output Goes to Stderr but Inconsistently

The `--explain` flag writes to stderr on some commands (search, init) which is correct behavior. However, it would be helpful to document this clearly in `--help` output, since agents may need to know where to read it.

### SUG-3: `review-due` Default Date

`review-due` without `--before` uses today's date as cutoff, which means it only shows already-overdue guardrails. A common use case is "what's coming up for review in the next 30 days?" — consider defaulting to 30 days from now, or at least mentioning the default in the help text.

### SUG-4: `check` Command Could Show Score Threshold Guidance

The `check` command returns matching guardrails with scores, but doesn't indicate whether the scores are high enough to be considered "relevant." Adding a `relevance` field (e.g., `high`/`medium`/`low`) or a `confidence` note would help agents decide whether to flag the match.

### SUG-5: `delete` Without `--confirm` Behavior

I did not test `delete` without `--confirm` (to avoid interactive prompts), but it would be good if `LLM=true` mode auto-confirms or if there's documentation about the behavior.

### SUG-6: Consider `applies_to` Taxonomy Validation

`scope` values are validated against `taxonomy.json`, but `applies_to` values (e.g., "technology", "security") are not validated against any taxonomy. Consider adding an `applies_to` taxonomy for consistency, or document that these are free-form.

---

## Commands Tested

| Command | Status | Notes |
|---------|--------|-------|
| `init` | Pass | Idempotent, creates correct file structure |
| `add` | Pass | Validates required fields, taxonomy, duplicate titles |
| `list` | Pass | Filters by severity, status work correctly |
| `search` | Pass* | Works but no minimum relevance threshold |
| `get` | Pass | Returns guardrail with refs and links |
| `update` | Pass | Patch semantics work correctly, updates `updated_at` |
| `check` | Pass | Returns ranked matches with severity summary |
| `link` | Pass | Creates typed relationships |
| `ref-add` | Pass | Adds references with all fields |
| `related` | Pass | Shows linked guardrails with direction |
| `deprecate` | Pass | Sets status, stores reason in metadata |
| `supersede` | Pass | Enforces valid transitions, creates link |
| `delete` | Pass | Removes guardrail, reports removed refs/links |
| `stats` | Pass | Correct counts by status/severity/scope |
| `review-due` | Pass | Works with `--before` flag |
| `deduplicate` | Pass | No false positives on distinct guardrails |
| `validate` | Pass | No errors on valid data |
| `build` | Pass | Rebuilds index, reports counts |
| `export` (json) | Pass | Complete data, roundtrip works |
| `export` (csv) | Fail | Missing rationale/guidance columns |
| `export` (markdown) | Pass | Excellent grouped output with refs |
| `import` (json) | Pass | Upsert works correctly |
| `import` (csv) | Fail | Fails due to missing columns from export |
| `guide` | Pass | Comprehensive schema output |
| `--version` | Pass | Shows "archguard 0.5.0" |
| `--format table` | Pass | Rich-formatted tables |
| `--explain` | Pass | Human-readable descriptions on stderr |
| `--schema` | Pass | JSON Schema for stdin inputs |
| `LLM=true` | Pass | Forces JSON, suppresses decoration |

---

## Performance Notes

- `init`: 7ms
- `add`: ~1000-1300ms (embedding generation dominates)
- `list` / `get` / `stats`: 2-5ms (fast reads from SQLite)
- `search`: ~900-1400ms (embedding + BM25 + RRF)
- `build`: ~1300ms (re-embeds all guardrails)
- `delete`: ~1500ms (rebuilds embeddings)
- `update` (no text change): 3ms
- `validate`: 27ms

The embedding step is the performance bottleneck. For batch operations, this is expected. Read operations are very fast.

---

## Conclusion

Archguard is a well-crafted tool that fills a real gap — providing a structured, queryable, Git-friendly store of architectural governance knowledge designed for both human and AI agent consumption. The CLI design is thoughtful, with consistent output envelopes, proper error codes, and excellent agent-facing features (`guide`, `--schema`, `--explain`, `LLM=true`).

The main issue to address is the **CSV export/import roundtrip bug** (BUG-1). The vector search relevance threshold (BUG-2) is a softer concern but worth considering for agent reliability. The suggestions are quality-of-life improvements rather than blockers.
