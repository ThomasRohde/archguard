# Archguard CLI Blackbox Feedback

Tested `archguard 1.5.0` on Windows PowerShell on March 6, 2026.

## What works well

- `archguard guide` is the strongest part of the product. It gives a machine-readable schema, workflow guidance, examples, error codes, and compatibility expectations in one call.
- The happy path works end to end: `init`, `add`, `list`, `search`, `check`, `get`, `review-due`, and `export` all worked against a fresh data directory.
- The JSON envelope is good for automation. `ok`, `errors`, `warnings`, `request_id`, and `metrics.duration_ms` make the CLI predictable for agents.
- Human-readable output is solid where it is implemented. `list`, `search`, `stats`, and `export` produced clean `table` / `markdown` output.
- Error codes were mostly consistent. Invalid JSON, duplicate title, and taxonomy mismatch all returned structured failures.

## Findings

### 1. `validate` does not enforce the tool's own "active guardrails need references" rule

The guide says:

- "Active guardrails have at least one authoritative reference."
- "Setting status=active without attaching references" is an anti-pattern.

Repro:

1. `archguard init -d sample-data`
2. Add an `active` guardrail with no `references`
3. Run `archguard validate -d sample-data`

Actual:

- `validate` returned no warnings and no errors.

Expected:

- At minimum, `validate` should warn.
- Better: `add` should reject `status=active` without references, or require an explicit override.

Impact:

- The CLI documents a governance rule but does not enforce or even surface drift against it.

### 2. `--format` is advertised as a global option but silently ignored by some commands

These commands still returned JSON:

- `archguard --format table init -d sample-data-5`
- `archguard --format markdown validate -d sample-data`
- `archguard --format markdown guide`

Meanwhile these commands did honor the format:

- `archguard --format table list -d sample-data`
- `archguard --format markdown search "managed database" -d sample-data`
- `archguard --format table stats -d sample-data`

Expected:

- Either every command should honor the global `--format`, or unsupported commands should fail clearly with a structured format error.

Impact:

- Silent fallback to JSON makes automation brittle and makes the CLI contract harder to trust.

### 3. Default duplicate detection missed an obvious near-duplicate

I added these two records:

- `Use managed databases for production workloads`
- `Prefer managed relational databases in production`

Results:

- `archguard deduplicate -d sample-data` returned no pairs at the default threshold `0.85`
- `archguard deduplicate -d sample-data --threshold 0.7` returned the pair with similarity `0.835`

Expected:

- The default threshold should catch a pair this close, especially because the bootstrap guidance explicitly tells agents to run `deduplicate` before creating records.

Impact:

- The documented workflow under-detects overlap unless the caller already knows to lower the threshold.

### 4. Validation failures leak raw framework internals instead of CLI-grade messages

Repro:

- Submit `archguard add` input missing `guidance`

Actual:

- The message includes raw Pydantic internals and a docs URL:
  `Validation failed: 1 validation error for GuardrailCreate ... For further information visit https://errors.pydantic.dev/...`

Expected:

- Something like: `Missing required field: guidance`

Impact:

- The CLI feels less polished than the rest of the API surface, and the error text is noisier than it needs to be for users or agents.

### 5. First write had noticeable cold-start latency

Observed behavior on this machine:

- First `archguard add` took more than 14 seconds and completed after my initial client timeout.
- Subsequent `add` operations were around 1.1 to 1.2 seconds.
- Read commands such as `search`, `check`, and `deduplicate` were typically around 2.3 to 3.0 seconds on a 3-record corpus.

Expected:

- If there is index or embedding warm-up, surface that clearly on stderr so the first write does not look hung.

Impact:

- The first-run experience is easy to misread as a stuck command.

## Smaller UX Notes

- `search "managed database"` returned `Encrypt customer data at rest` as a `vector`-only `medium` match. On a tiny corpus this felt like a false positive and suggests the semantic search weighting may be a bit loose.
- `-h` is not accepted; only `--help` works. That is not wrong, but it is unexpected relative to most CLIs.

## Overall

The core shape is good. `guide` in particular is unusually strong and makes the CLI much easier to automate than most tools in this category. The biggest issues are consistency and policy enforcement: the product tells users to rely on certain invariants, but today some of those invariants are advisory only, and some global options are only partially implemented.
