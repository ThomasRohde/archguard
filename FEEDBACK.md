# Review Feedback

## Findings

1. **High: invalid date strings are accepted and later crash read/export paths**

   Files:
   `src/archguard/core/models.py:33-36`
   `src/archguard/core/models.py:80`
   `src/archguard/cli/maintenance.py:50`
   `src/archguard/cli/maintenance.py:104-105`
   `src/archguard/output/markdown.py:117`
   `src/archguard/output/markdown.py:169`
   `src/archguard/output/markdown.py:258`

   Why this matters:
   `review_date`, `created_at`, `updated_at`, and `added_at` are modeled as plain `str`, so `add`, `update`, and `import` accept invalid values. Later code assumes valid ISO dates and either compares them lexicographically or calls `date.fromisoformat(...)`, which raises at runtime.

   Repro:
   ```powershell
   uv run archguard --data-dir $dir init | Out-Null
   '{"title":"Bad review","severity":"must","rationale":"r","guidance":"g","scope":["it-platform"],"applies_to":["service"],"owner":"o","review_date":"not-a-date"}' | uv run archguard --data-dir $dir add | Out-Null
   uv run archguard --data-dir $dir export --format markdown
   ```
   This crashes with `ValueError: Invalid isoformat string: 'not-a-date'`.

   Recommended fix:
   Use real Pydantic date/datetime types, normalize them on write, and reject invalid input in `add`, `update`, and `import`. That also removes the current string-comparison bugs in `stats`, `list --review-before`, and `review-due`.

2. **High: `import` claims upsert-by-ID, but the implementation ignores IDs and generates new ones**

   Files:
   `src/archguard/cli/maintenance.py:209-211`
   `src/archguard/cli/maintenance.py:224`
   `src/archguard/cli/maintenance.py:241`
   `src/archguard/cli/maintenance.py:281-330`

   Why this matters:
   The command description says import matches on "ID or title", but records are validated through `GuardrailCreate`, which has no `id` field, and existing rows are indexed only by title. Any supplied ID is silently discarded and new guardrails get fresh ULIDs. That breaks identity preservation for re-imports, cross-file references, supersession chains, and exported/imported round-trips.

   Repro:
   ```powershell
   Set-Content -Path $import -Value '[{"id":"01ARZ3NDEKTSV4RRFFQ69G5FAV","title":"Imported","severity":"must","rationale":"r","guidance":"g","scope":["it-platform"],"applies_to":["service"],"owner":"o"}]' -Encoding UTF8
   uv run archguard --data-dir $dir import $import | Out-Null
   Get-Content (Join-Path $dir 'guardrails.jsonl')
   ```
   The stored record gets a new ULID instead of `01ARZ3NDEKTSV4RRFFQ69G5FAV`.

   Recommended fix:
   Introduce a dedicated import model that optionally accepts `id`, `created_at`, and `updated_at`, then upsert by ID first and title second.

3. **Medium: several mutating commands leave `.guardrails.db` stale even though the PRD says every write rebuilds the index**

   Files:
   `PRD.md:206-215`
   `src/archguard/cli/write.py:143-233`
   `src/archguard/cli/write.py:236-298`
   `src/archguard/cli/write.py:301-356`
   `src/archguard/cli/write.py:433-484`
   `src/archguard/cli/write.py:487-560`
   `src/archguard/cli/maintenance.py:200-337`

   Why this matters:
   `update`, `ref-add`, `link`, `deprecate`, `supersede`, and `import` mutate JSONL but never rebuild the derived SQLite index before returning. Lazy rebuild on the next read masks this during normal CLI usage, but it still violates the documented write contract and leaves the repository in an internally inconsistent state after a successful write command.

   Repro:
   ```powershell
   $before=(Get-Item (Join-Path $dir '.guardrails.db')).LastWriteTimeUtc
   '{"guidance":"updated"}' | uv run archguard --data-dir $dir update $id | Out-Null
   $after=(Get-Item (Join-Path $dir '.guardrails.db')).LastWriteTimeUtc
   ```
   `LastWriteTimeUtc` is unchanged after `update`.

   Recommended fix:
   Rebuild the index after every successful mutation, or explicitly change the contract and docs if write commands are intentionally JSONL-only.

4. **Medium: `check` silently discards all but the first `scope` and `applies_to` filter**

   Files:
   `src/archguard/core/models.py:130-133`
   `src/archguard/cli/read.py:326-337`

   Why this matters:
   The input schema advertises arrays, but the implementation only uses `context["scope"][0]` and `context["applies_to"][0]`. That creates false negatives whenever the matching scope or applies-to tag is not first in the input.

   Repro:
   ```powershell
   '{"decision":"kafka","scope":["channels","it-platform"]}' | uv run archguard --data-dir $dir check
   ```
   With a matching `it-platform` guardrail present, this returns no matches because only `channels` is used.

   Recommended fix:
   Validate stdin with `CheckContext`, then make the array semantics explicit and implement them consistently in `hybrid_search` filtering.

5. **Medium: the CLI has drifted from the documented architecture invariants**

   Files:
   `AGENTS.md:30`
   `AGENTS.md:36`
   `PRD.md:87`
   `PRD.md:783`
   `src/archguard/core/models.py:57`
   `src/archguard/cli/write.py:359-430`
   `src/archguard/cli/guide.py:314-332`

   Why this matters:
   The project instructions say "No delete command (deprecate/supersede only)", but the CLI implements and documents a destructive `delete` command. The data model and CLI also accept a `requires` link type that is not in the PRD's link vocabulary. This is more than doc drift: it changes lifecycle and relationship semantics in a way future contributors will treat as supported because the guide exposes it.

   Recommended fix:
   Either remove `delete` and `requires`, or update the authoritative docs after an explicit design decision. Right now the code, guide, and PRD are not describing the same product.

6. **Medium: `--schema` support is inconsistent, and `init --schema` still mutates state**

   Files:
   `AGENTS.md:30`
   `src/archguard/cli/setup.py:16-25`
   `src/archguard/cli/setup.py:35-76`
   `src/archguard/cli/read.py:15-355`
   `src/archguard/cli/guide.py:154-240`
   `src/archguard/cli/guide.py:355-420`

   Why this matters:
   The instructions say all read commands support `--schema`, but only `check` does. `search --schema` fails at argument parsing. Separately, `init` advertises a `--schema` option but ignores it and proceeds with filesystem writes.

   Repro:
   ```powershell
   uv run archguard search --schema foo
   uv run archguard --data-dir $dir init --schema
   ```
   The first errors with "No such option: --schema"; the second initializes the directory instead of printing a schema.

   Recommended fix:
   Decide whether `--schema` is part of the supported contract. If yes, implement it consistently and ensure it exits without side effects. If not, remove it from docs and signatures.

## Testing Gaps

- The automated suite is clean: `uv run pytest`, `uv run ruff check src tests`, and `uv run pyright src` all passed.
- The current tests miss the cases above: invalid date rejection, ID-preserving import, multi-value `check` filters, post-write index freshness, and `--schema` coverage for commands beyond `add`/`check`.
- Some tests appear to codify current drift rather than the PRD, for example the guide currently expects `delete` to be a supported command.

## Summary

The codebase is in decent mechanical shape: the structure is clear, the test suite is large, and lint/type-checking are clean. The main risks are contract mismatches and latent runtime bugs in paths the current tests do not exercise, especially around date validation, identity preservation during import, and write-side index freshness.
