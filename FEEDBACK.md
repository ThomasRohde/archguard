# Archguard CLI v0.4.0 — Blackbox Test Feedback

**Date:** 2026-03-06
**Tester:** Claude (automated blackbox test)
**Platform:** Windows 11 / Git Bash

---

## Overall Impression

Archguard is a well-designed, focused CLI for managing architecture guardrails. The core workflow — init, add, search, check — works smoothly and the tool feels production-ready for its stated purpose. The structured JSON envelope, error codes, and deterministic behavior make it excellent for agent integration. Performance is good (most operations <500ms, search/embed ~400-600ms).

**Rating: 4/5** — solid tool with a few rough edges.

---

## What Works Well

1. **Structured JSON envelope** — Every response includes `ok`, `errors`, `warnings`, `metrics`, and `request_id`. This is best-in-class for CLI-to-agent communication. The `suggested_action` field on errors is a great touch.

2. **Hybrid search** — BM25 + vector search with RRF fusion works well. The `match_sources` field showing which retrieval method contributed is excellent for debugging and trust.

3. **`guide` command** — Returning the full CLI schema as JSON is a brilliant design for agent bootstrap. One call gives an agent everything it needs to use the tool correctly.

4. **`--explain` flag** — Outputs a plain-English explanation of what a command does. Great for agents and humans alike.

5. **`--schema` flag on `add`** — Emitting the JSON Schema for input is very helpful. Agents can use this to self-validate before calling.

6. **Error handling** — Clear error codes, appropriate exit codes (10 for validation, 40 for conflict, 50 for I/O), and actionable error messages. Validation errors list all missing fields at once rather than failing on the first one.

7. **Git-friendly data** — JSONL files, `.gitignore` for the SQLite index, and idempotent `init` (safe to re-run without data loss) are all the right choices.

8. **Lifecycle management** — The `deprecate` → `supersede` workflow with automatic link creation and status transition guards (can't deprecate a superseded guardrail) is well thought out.

9. **Table/markdown output** — `--format table` produces clean, readable tables. `--format markdown` on `export` generates well-structured documentation grouped by scope.

10. **`check` command** — The decision-checking workflow returns matched guardrails with a severity summary (`must`/`should`/`may` counts), which is exactly what an agent needs to assess compliance.

---

## Bugs

### BUG-1: `--format` / `-f` only works as a global option before the subcommand

```
archguard list -f table          # ERROR: "No such option: -f"
archguard --format table list    # Works
```

The help text shows `-f` as a global option, but most CLIs allow global options to appear anywhere. At minimum, this is confusing because the help output shows `-f` alongside `--format` under "Options", and users will naturally try to put it after the subcommand. **Suggestion:** Either make `-f` work in both positions, or document this limitation clearly.

### BUG-2: `check --schema` does not output the schema

```
archguard check --schema         # Reads stdin, then fails with ERR_VALIDATION_JSON
echo '{}' | archguard check --schema  # Fails with ERR_VALIDATION_INPUT
```

The `--schema` flag on `add` correctly outputs the JSON Schema and exits. On `check`, it still tries to read and validate stdin instead of outputting the schema. **Expected:** `check --schema` should print the `CheckContext` schema and exit, like `add --schema` does.

### BUG-3: `--format markdown` on `search` outputs JSON

```
archguard --format markdown search "encryption"   # Outputs JSON envelope, not markdown
```

The `--format table` works correctly for `search`, but `--format markdown` silently falls back to JSON output. **Expected:** Either render search results as a markdown table, or return an error saying markdown format is not supported for this command.

---

## Minor Issues / Suggestions

### MINOR-1: `export --format markdown` output is correct but verbose for multi-scope guardrails

Guardrails with multiple scopes (e.g., `["it-platform", "channels"]`) are duplicated under each scope section. This is arguably correct (scope-grouped view), but could confuse users who expect a flat list. Consider adding a `--group-by` flag or a flat export mode.

### MINOR-2: `list --top N` reports `total` as the unfiltered count

```json
{"guardrails": [/* 2 items */], "total": 5}
```

When using `--top 2`, the response shows 2 guardrails but `total: 5`. This is arguably correct (total in corpus vs. returned), but could be clearer. Consider renaming to `total_in_corpus` or adding a `returned` field.

### MINOR-3: `search ""` (empty query) returns all guardrails ranked by vector similarity

An empty search query silently returns all guardrails scored by vector similarity to an empty string. This works but the scores are meaningless (0.015–0.016 range). Consider either: (a) returning an error for empty queries, or (b) documenting this as the "list all, vector-ranked" behavior.

### MINOR-4: `search` returns deprecated and superseded guardrails by default

Active, draft, deprecated, and superseded guardrails are all returned in search results. For the primary use case (agent checking "what rules apply?"), returning deprecated/superseded guardrails may cause confusion. Consider defaulting to `--status draft,active` or at least flagging deprecated results more prominently.

### MINOR-5: No `delete` command

There is no way to delete a guardrail. The lifecycle goes draft → active → deprecated/superseded, but sometimes you just need to remove a test entry or fix a mistake. Users must manually edit the JSONL file and rebuild. Consider adding `archguard delete ID --confirm` for this purpose.

### MINOR-6: `init` is silently idempotent with no "already exists" warning

Running `init` on an existing directory returns `ok: true` with `"message": "Initialized guardrails repository"` and no warnings. While the data is preserved (good!), a warning like `"Data directory already exists; skipping"` would be more informative.

### MINOR-7: `add --schema` output goes to stdout but doesn't set `ok: true` envelope

The `add --schema` command outputs raw JSON Schema without the standard envelope. This is fine for human use, but breaks the contract for agents that always expect the envelope. Consider wrapping it: `{"ok": true, "result": {"schema": {...}}}`.

### MINOR-8: Help text says `guardrails` but binary is `archguard`

The quick-start section in `--help` shows:
```
guardrails init
guardrails add < g.json
guardrails search 'api'
```

But the actual binary name is `archguard`. This will confuse users who copy-paste from the help text.

---

## Feature Requests

1. **`archguard diff`** — Show changes between the current JSONL state and the SQLite index (i.e., what would `build` do?). Useful for CI pipelines.

2. **`archguard activate ID`** — Transition from `draft` to `active`. Currently you have to use `update` with `{"status": "active"}`, which is verbose and not discoverable.

3. **CSV import** — The `import` command accepts `.json` and `.csv` but the CSV format is undocumented. What columns are expected? A `--dry-run` flag would also be valuable.

4. **`check` with `--status` filter** — The `check` command doesn't accept `--status`, so it matches against all guardrails including deprecated ones. Adding `--status active` would let agents check only against active rules.

---

## Summary

Archguard is a thoughtfully designed tool that gets the fundamentals right: deterministic behavior, structured output, hybrid search, and Git-friendly storage. The `guide` command and structured error codes make it one of the most agent-friendly CLIs I've tested. The bugs found are minor (format flag positioning, `check --schema`, markdown format on search) and the suggestions are mostly polish. Ready for production use with the caveats noted above.
