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

`archguard init` creates the JSONL repository files and taxonomy. The SQLite index and embedding vectors are built lazily on the first `add`, `search`, or `build`.

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

## Global options

```
-f, --format   Output format: json (default), table, markdown
-d, --data-dir Path to data directory (default: guardrails)
-q, --quiet    Suppress stderr progress messages
```

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
