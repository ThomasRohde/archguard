# guardrails-cli

Architecture guardrails management CLI -- a queryable store of architectural constraints, standards, and rules backed by full-text search (BM25) and vector similarity (semantic search).

## Status

**Pre-release / Scaffold** -- Core structure is in place, commands are stubbed with guided TODOs. See [docs/ROADMAP.md](docs/ROADMAP.md) for milestones.

## Who is this for?

- **AI agents** that need programmatic access to governance knowledge for architectural decisions.
- **Enterprise architects** who need a single, authoritative source of guardrails.
- **Platform teams** maintaining architectural standards across an organisation.

## Quick start

```bash
# Install uv if you haven't already
# https://docs.astral.sh/uv/getting-started/installation/

# Clone and install
git clone <repo-url> && cd archguard
uv sync

# Initialize a guardrails repository
uv run guardrails init

# Run tests
uv run pytest
```

## Repository structure

```
archguard/
├── PRD.md                         # Product requirements (source of truth)
├── CLI-MANIFEST.md                # Agent-friendly CLI contract
├── pyproject.toml                 # Python project config (uv/hatch)
├── src/guardrails_cli/
│   ├── __main__.py                # Entry point
│   ├── cli/                       # Typer command definitions
│   │   ├── setup.py               # init, build, validate
│   │   ├── write.py               # add, update, ref-add, link, deprecate, supersede
│   │   ├── read.py                # search, get, related, list, check
│   │   ├── export.py              # export
│   │   └── maintenance.py         # stats, review-due, deduplicate, import
│   ├── core/                      # Business logic
│   │   ├── models.py              # Pydantic models
│   │   ├── store.py               # JSONL read/write
│   │   ├── index.py               # SQLite index
│   │   ├── search.py              # Hybrid search (BM25 + vector + RRF)
│   │   ├── embeddings.py          # Model2Vec wrapper
│   │   └── validator.py           # Integrity checks
│   └── output/                    # Output formatting
│       ├── json.py                # orjson serialization
│       ├── table.py               # Rich tables
│       └── markdown.py            # Markdown export
├── tests/                         # pytest + hypothesis
├── docs/                          # Project documentation
└── .github/                       # CI and agent instructions
```

## Commands overview

| Command | Description |
|---------|-------------|
| `guardrails init` | Create data directory and download model |
| `guardrails add < g.json` | Add a guardrail from stdin |
| `guardrails search "query"` | Hybrid BM25 + vector search |
| `guardrails check < context.json` | Validate a decision against guardrails |
| `guardrails list --status active` | List with filters |
| `guardrails export --format markdown` | Export for publishing |

See `guardrails --help` for the full command surface.

## Running tests

```bash
uv run pytest              # All tests
uv run pytest -x           # Stop on first failure
uv run pytest -k test_models  # Run specific test module
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
