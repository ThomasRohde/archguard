# archguard

[![PyPI version](https://img.shields.io/pypi/v/archguard)](https://pypi.org/project/archguard/)
[![Python 3.12+](https://img.shields.io/pypi/pyversions/archguard)](https://pypi.org/project/archguard/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Architecture guardrails management CLI -- a queryable store of architectural constraints, standards, and rules backed by full-text search (BM25) and vector similarity (semantic search).

## Who is this for?

- **AI agents** that need programmatic access to governance knowledge for architectural decisions.
- **Enterprise architects** who need a single, authoritative source of guardrails.
- **Platform teams** maintaining architectural standards across an organisation.

## Installation

```bash
pip install archguard
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install archguard
```

## Quick start

`archguard init` creates the JSONL repository files and taxonomy. By default, `taxonomy.json` starts with an empty `scope` array, which means `scope` is free-form until you decide to lock it down. The SQLite index and embedding vectors are built lazily on the first `add`, `search`, or `build`.

### POSIX shells

```bash
# Initialize a guardrails repository
archguard init

# Add a guardrail from stdin
echo '{"title":"Prefer managed services","severity":"should","rationale":"Reduce ops","guidance":"Use managed offerings","scope":["it-platform"],"applies_to":["technology"],"owner":"Platform Team"}' | archguard add

# Search guardrails
archguard search "managed services"

# Check a decision against guardrails
echo '{"decision":"Use self-hosted Kafka"}' | archguard check

# List, filter, and export
archguard list --status active --severity must
archguard export --format markdown
archguard -f table stats
```

### PowerShell

```powershell
# Initialize a guardrails repository
archguard init

# Add a guardrail from a JSON file on stdin
Get-Content .\g.json | archguard add

# Check a decision against guardrails
Get-Content .\decision.json | archguard check

# Update and ref-add also read JSON from stdin
Get-Content .\patch.json | archguard update 01HXYZ...
Get-Content .\reference.json | archguard ref-add 01HXYZ...
```

## Understanding taxonomy

In `archguard`, the taxonomy is a controlled vocabulary for the `scope` field.

- `scope` answers **which architectural domain this guardrail belongs to**.
- The allowed values live in `taxonomy.json` inside your data directory.
- The taxonomy is **versioned with your repository**, so teams and agents share the same vocabulary.
- Only `scope` is taxonomy-validated. Fields such as `applies_to` remain free-form.

### What taxonomy is for

Use taxonomy values for broad, reusable architectural domains such as:

- `it-platform`
- `data-platform`
- `channels`
- `risk-management`

Good taxonomy values are:

- stable over time,
- shared across many guardrails,
- useful for filtering and reporting.

Taxonomy values are **not** the place for highly specific technologies or one-off keywords. Put those in the guardrail text, references, or decision context instead.

### Two operating modes

#### Free-form mode

If `taxonomy.json` contains:

```json
{
    "scope": []
}
```

then `scope` is unconstrained. This is useful when you are:

- bootstrapping a repository quickly,
- importing messy source material,
- still discovering the right domain vocabulary.

Example:

```json
{
    "title": "Encrypt database backups",
    "severity": "must",
    "rationale": "Backups contain sensitive production data.",
    "guidance": "All production backups must be encrypted at rest.",
    "scope": ["security-operations"],
    "applies_to": ["technology"],
    "owner": "Platform Team"
}
```

That record is accepted even if `security-operations` is not yet standardised, because the taxonomy is empty.

#### Controlled vocabulary mode

If `taxonomy.json` contains values, `archguard` validates every `scope` entry against them.

Example `taxonomy.json`:

```json
{
    "scope": [
        "business-control",
        "business-support",
        "channels",
        "data-platform",
        "it-platform",
        "organisational-support",
        "products-and-services",
        "relationships",
        "risk-management"
    ]
}
```

With a populated taxonomy:

- `archguard add` rejects unknown `scope` values,
- `archguard update` rejects invalid replacement scopes,
- `archguard validate` reports taxonomy mismatches,
- `archguard list --scope ...` and `archguard search --scope ...` become much more reliable.

If a guardrail uses a scope value that is not in the taxonomy, the command fails with a validation error.

### Recommended workflow

For most teams, the smoothest path is:

1. Start in free-form mode with `archguard init`.
2. Add real guardrails from source material.
3. Review the recurring `scope` labels you actually use.
4. Turn those into a small controlled vocabulary in `taxonomy.json`.
5. Run `archguard validate` to catch any outliers or spelling drift.

This keeps the early ingestion flow fast while still letting you converge on a clean, reviewable taxonomy.

### Bootstrapping a taxonomy on day one

If you already know your architectural domains, initialize the repository with a taxonomy file:

```bash
archguard init --taxonomy team-taxonomy.json
```

Example `team-taxonomy.json`:

```json
{
    "scope": [
        "customer-channels",
        "data-platform",
        "integration-platform",
        "risk-management"
    ]
}
```

This is a good fit when:

- your enterprise already has a stable architecture map,
- multiple teams or agents will add guardrails,
- you want validation from the first commit.

### How taxonomy affects day-to-day use

Once you standardise `scope`, the same values flow through the whole CLI:

- authoring: `scope` in `archguard add` and `archguard update`
- filtering: `archguard list --scope it-platform`
- search narrowing: `archguard search "managed services" --scope it-platform`
- decision checks: include matching `scope` values in the JSON passed to `archguard check`
- reporting: exports and stats group cleanly because the domain labels are consistent

Example decision context:

```json
{
    "decision": "Use self-hosted Kafka for event streaming",
    "scope": ["it-platform", "data-platform"],
    "applies_to": ["technology", "platform"]
}
```

### Practical tips

- Keep taxonomy values short, lowercase, and kebab-case.
- Prefer a small set of durable domains over dozens of near-duplicates.
- Treat taxonomy updates as governance changes: review them in pull requests.
- If you need rich detail, add it to the guardrail text or references instead of overloading `scope`.
- When in doubt, start broader. You can refine later without inventing a taxonomy worthy of a biology textbook.

## Commands

| Command | Description |
|---------|-------------|
| `archguard init` | Create repository files and taxonomy; search index warms lazily |
| `archguard add` | Add a guardrail (reads JSON from stdin) |
| `archguard get <id>` | Get full detail for a guardrail |
| `archguard list` | List guardrails with filters |
| `archguard search <query>` | Hybrid BM25 + vector search |
| `archguard check` | Validate a decision against the corpus |
| `archguard update <id>` | Patch a guardrail (reads JSON from stdin) |
| `archguard deprecate <id>` | Mark a guardrail as deprecated |
| `archguard supersede <id> --by <new_id>` | Replace one guardrail with another |
| `archguard ref-add <id>` | Add a reference to a guardrail |
| `archguard link <from> <to>` | Create a relationship between guardrails |
| `archguard related <id>` | Show linked guardrails |
| `archguard export` | Export as JSON, CSV, or Markdown |
| `archguard import <file>` | Bulk import from JSON or CSV |
| `archguard stats` | Counts by status, severity, scope |
| `archguard review-due` | List guardrails past their review date |
| `archguard deduplicate` | Detect likely duplicates |
| `archguard build` | Rebuild the search index |
| `archguard validate` | Check data integrity |

Every command supports `--explain` for a description and `--help` for usage.

For compact, highly normative corpora, `archguard deduplicate` defaults to a threshold of `0.65` so short near-duplicates are easier to catch without immediately dropping into manual tuning.

## Authoring guardrails safely

- Keep records **atomic**: one rule per guardrail.
- Use `status: "draft"` when owner, scope, lifecycle stage, or review timing must be inferred.
- Keep `owner` required, but use a neutral placeholder such as `unassigned` for incomplete draft captures instead of inventing a precise team.
- Do not invent `review_date` from generic source material; only set it from repository policy or human input.
- `active` guardrails are stricter than drafts: they must have at least one authoritative reference, at least one non-empty `excerpt` preserving the evidence, and a non-placeholder owner.
- Record inferred/defaulted decisions in `metadata` when useful, for example under `metadata.field_derivation`.

## Global options

```
-f, --format   Output format: json (default), table, markdown
-d, --data-dir Path to data directory (default: guardrails)
-q, --quiet    Suppress stderr progress messages
```

## Exit codes

`archguard` uses stable process exit codes so shells, CI, and agents can branch without parsing prose:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `10` | Not found |
| `11` | Already exists |
| `12` | Invalid transition |
| `20` | Validation error |
| `21` | Integrity error |
| `30` | Build error |
| `31` | Model error |
| `40` | I/O error |
| `50` | Internal error |

## Output formats

- **JSON** (default): Machine-readable, enveloped `{"ok": true, ...}`
- **Table**: Rich terminal tables with color-coded severity
- **Markdown**: Confluence-ready export with grouped sections

## Development

```bash
git clone https://github.com/archguard/archguard && cd archguard
uv sync

uv run pytest              # 179 tests
uv run ruff check src/     # Lint
```

## Repository structure

```
src/archguard/
├── __main__.py            # Entry point
├── cli/                   # Typer command definitions
│   ├── setup.py           # init, build, validate
│   ├── write.py           # add, update, ref-add, link, deprecate, supersede
│   ├── read.py            # search, get, related, list, check
│   ├── export.py          # export
│   └── maintenance.py     # stats, review-due, deduplicate, import
├── core/                  # Business logic
│   ├── models.py          # Pydantic models
│   ├── store.py           # JSONL read/write
│   ├── index.py           # SQLite index (FTS5)
│   ├── search.py          # Hybrid search (BM25 + vector + RRF)
│   ├── embeddings.py      # Model2Vec wrapper
│   └── validator.py       # Integrity checks
└── output/                # Output formatting
    ├── json.py            # orjson serialization
    ├── table.py           # Rich tables
    └── markdown.py        # Markdown export
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
