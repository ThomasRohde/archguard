# PRD: `guardrails-cli` — Architecture Guardrails Management

**Status:** Draft  
**Version:** 1.0  
**Owner:** EA Team  
**Last updated:** 2026-03-05  
**CLI Manifest:** This tool conforms to the [Agent-Friendly CLI Manifest](./CLI-MANIFEST.md)

---

## Table of Contents

1. [Problem](#1-problem)
2. [Goals](#2-goals)
3. [Non-Goals](#3-non-goals)
4. [Key Concepts](#4-key-concepts)
5. [Data Model](#5-data-model)
6. [Storage Architecture](#6-storage-architecture)
7. [Embedding Model](#7-embedding-model)
8. [Workflows](#8-workflows)
9. [Command Surface](#9-command-surface)
10. [Search and Retrieval](#10-search-and-retrieval)
11. [CLI Design Principles](#11-cli-design-principles)
12. [Error Handling and Exit Codes](#12-error-handling-and-exit-codes)
13. [Export and Publishing](#13-export-and-publishing)
14. [CI/CD Integration](#14-cicd-integration)
15. [Implementation Stack](#15-implementation-stack)
16. [Project Structure](#16-project-structure)
17. [Pydantic Models](#17-pydantic-models)
18. [Acceptance Criteria](#18-acceptance-criteria)
19. [MVP Milestones](#19-mvp-milestones)
20. [Open Questions](#20-open-questions)

---

## 1. Problem

Architecture guardrails — the constraints, standards, and rules that govern how systems are designed, built, and integrated — are scattered across Confluence pages, Word documents, PowerPoint decks, and people's heads. When an AI agent (or a human architect) needs to answer "what rules apply to this decision?", there is no queryable, authoritative source.

This creates two concrete problems:

1. **Governance consultation is slow.** Finding relevant guardrails for an architectural decision requires manual searching across multiple sources and asking colleagues. Agents have no programmatic access to governance knowledge at all.

2. **Guardrails go stale.** Without a structured lifecycle (draft → active → deprecated → superseded), guardrails accumulate without review. Nobody knows which are current, which conflict, or which have been superseded by newer policy.

---

## 2. Goals

1. Provide a **single, queryable store** of architecture guardrails backed by full-text search (BM25) and vector similarity (semantic search).
2. Enable AI agents to **ingest guardrails from source documents** — extracting, deduplicating, and enriching them with references and citations.
3. Support **governance consultation** — agents and humans can ask "what guardrails apply?" and receive ranked, relevant results.
4. Support **structured validation** — check a proposed architectural decision against the guardrail corpus.
5. Store everything as **Git-friendly JSONL files** — reviewable in PRs, diffable, mergeable.
6. Conform to the [Agent-Friendly CLI Manifest](./CLI-MANIFEST.md) — JSON-first output, stable exit codes, progressive discoverability.

---

## 3. Non-Goals

- No LLM inference inside the CLI. The tool is deterministic. The agent provides the intelligence.
- No cloud sync, API server, or multi-machine replication.
- No GUI. Humans interact via CLI or by reading exported Markdown/CSV.
- No automatic conflict resolution between guardrails. The CLI surfaces conflicts; humans resolve them.
- No `delete` command. Guardrails are deprecated or superseded, never deleted. The governance audit trail matters.

---

## 4. Key Concepts

### 4.1 Guardrail

A named, scoped architectural constraint. A guardrail says: "When you are making an architectural decision in *this context*, *this rule* applies." Guardrails have severity levels following RFC 2119 language:

| Severity | Meaning |
|----------|---------|
| `must` | Mandatory. Violation requires formal exception process. |
| `should` | Strongly recommended. Deviation requires documented rationale. |
| `may` | Advisory. Recommended practice, not enforced. |

### 4.2 Reference

An external citation linking a guardrail to its authoritative source: an Architecture Decision Record (ADR), a policy document, a regulation, a standard, or a pattern.

### 4.3 Link

A typed relationship between two guardrails: `supports`, `conflicts`, `refines`, or `implements`.

### 4.4 Scope and Applicability

Guardrails are tagged with structured metadata that enables deterministic filtering:

- **scope** — The architectural domain. Values are defined in a configurable taxonomy file loaded during `guardrails init`. Example values: `channels`, `relationships`, `business-support`, `products-services`, `business-control`, `risk-management`, `organisational-support`, `it-platform`, `data-platform`.
- **applies_to** — The type of architectural artifact: `application`, `technology`, `platform`, `service`, `api`, etc.
- **lifecycle_stage** — When in the technology lifecycle the guardrail is relevant: `acquire`, `build`, `operate`, `retire`.

---

## 5. Data Model

### 5.1 Guardrail Record

```
guardrail
├── id              (ULID — sortable, timestamp-embedded, collision-free)
├── title           (short name, e.g. "Prefer managed services over self-hosted")
├── status          (draft | active | deprecated | superseded)
├── severity        (must | should | may)
├── rationale       (why this guardrail exists)
├── guidance        (what to do — the actionable part)
├── exceptions      (when it is acceptable to deviate)
├── consequences    (what happens on violation)
├── scope           (JSON array: values from configured taxonomy, e.g. ["it-platform", "data-platform"])
├── applies_to      (JSON array: ["application", "technology", "platform"])
├── lifecycle_stage (JSON array: ["acquire", "build", "retire"])
├── owner           (person or team accountable)
├── review_date     (next scheduled review, ISO 8601)
├── superseded_by   (ULID of replacement guardrail, nullable)
├── created_at      (ISO 8601)
├── updated_at      (ISO 8601)
└── metadata        (JSON object for extensibility)
```

Authoring policy note:

- `owner` remains required in the creation contract to preserve accountability.
- When the source does not identify an accountable owner, agents should use a neutral placeholder such as `unassigned`, mark the record as `draft`, and record the defaulting decision in `metadata`.
- Agents must not invent precise governance metadata such as owner or review date from generic source material.

### 5.2 Reference Record

```
reference
├── guardrail_id    (ULID — FK to guardrail)
├── ref_type        (adr | policy | standard | regulation | pattern | document)
├── ref_id          (external identifier, e.g. "ADR-042")
├── ref_title       (human-readable title of the source)
├── ref_url         (URL to the source, nullable)
├── excerpt         (relevant quote or passage from the source)
└── added_at        (ISO 8601)
```

For `active` guardrails, at least one reference must preserve evidence in `excerpt`; a URL alone is not sufficient.

### 5.3 Link Record

```
link
├── from_id         (ULID — FK to guardrail)
├── to_id           (ULID — FK to guardrail)
├── rel_type        (supports | conflicts | refines | implements)
└── note            (optional annotation)
```

---

## 6. Storage Architecture

### 6.1 Design Principle: JSONL is Source, SQLite is Index

SQLite is binary and cannot be meaningfully diffed, reviewed, or merged in Git. Therefore:

- **JSONL files are the source of truth.** They are committed to Git.
- **SQLite is a derived runtime artifact.** It is gitignored and rebuilt from JSONL.

### 6.2 Repository Structure

```
guardrails/
├── taxonomy.json             # Scope vocabulary (created during init)
├── guardrails.jsonl          # One guardrail per line (source of truth)
├── references.jsonl          # One reference per line
├── links.jsonl               # One link per line
├── models/                   # Bundled embedding model (committed)
│   └── potion-base-8M/      # Model2Vec static model (~8 MB)
│       ├── config.json
│       ├── model.safetensors
│       └── tokenizer.json
├── .guardrails.db            # Gitignored — rebuilt from JSONL
└── .gitignore                # Contains: .guardrails.db
```

### 6.3 JSONL Format

Each line in `guardrails.jsonl` is a self-contained JSON object:

```json
{"id":"01JG5K...","title":"Prefer managed services","status":"active","severity":"should","rationale":"Managed services reduce operational burden...","guidance":"When evaluating...","exceptions":"Acceptable when...","scope":["it-platform","organisational-support"],"applies_to":["technology","platform"],"lifecycle_stage":["acquire"],"owner":"Platform Team","review_date":"2026-09-01","superseded_by":null,"created_at":"2025-06-15T10:30:00Z","updated_at":"2026-01-20T14:15:00Z","metadata":{}}
```

JSONL is line-oriented: adding a guardrail appends a line; updating one changes a single line. Git diffs are clean, merge conflicts are per-guardrail, and code review shows exactly which guardrail changed.

### 6.4 SQLite Index

The `.guardrails.db` file contains:

- **Relational tables** mirroring the JSONL structure for efficient filtering.
- **FTS5 virtual table** indexing: `title`, `rationale`, `guidance`, `exceptions`, `scope` (BM25 full-text search).
- **Vector embeddings** stored as BLOBs for cosine similarity search.
- **Schema version table** with a single integer for migration detection.

SQLite configuration follows established patterns:

```python
conn.execute("PRAGMA journal_mode=WAL")        # Concurrent readers
conn.execute("PRAGMA synchronous=NORMAL")       # Safe with WAL
conn.execute("PRAGMA cache_size=-64000")         # 64 MB cache
conn.execute("PRAGMA temp_store=MEMORY")
conn.execute("PRAGMA foreign_keys=ON")
```

FTS5 uses `unicode61` tokenizer with `remove_diacritics 2` for English/Danish content.

### 6.5 Build Step

Every mutating command follows the same pattern:

```
[agent calls CLI]
    → validate input (Pydantic)
    → write to JSONL (source of truth)
    → rebuild SQLite index
    → return result as JSON
```

The `guardrails build` command explicitly rebuilds the full index:

```
Read JSONL → Validate (Pydantic) → INSERT rows → Build FTS5 → Compute embeddings → Store vectors
```

### 6.6 Lazy Auto-Build

Every read command checks if `.guardrails.db` is older than the JSONL files (mtime comparison). If stale or missing, the index is rebuilt automatically before querying. This is transparent to the agent — zero setup, always correct.

### 6.7 Edit Semantics

Mutations use **rewrite-on-edit**: read all lines, find matching ID, replace that line, write the whole file back. This is simple, correct, and performant at the scale of hundreds to low thousands of guardrails. Git history provides the audit trail.

### 6.8 Taxonomy File

The `taxonomy.json` file defines the allowed values for the `scope` field. It is created during `guardrails init` and committed to Git alongside the JSONL files.

```json
{
  "scope": [
    "channels",
    "relationships",
    "business-support",
    "products-services",
    "business-control",
    "risk-management",
    "organisational-support",
    "it-platform",
    "data-platform"
  ]
}
```

`guardrails init --taxonomy <file>` accepts a JSON file with a `scope` array to bootstrap the taxonomy. If omitted, `init` creates a `taxonomy.json` with an empty `scope` array, and scope values are unconstrained until the file is populated.

The Pydantic validation layer reads `taxonomy.json` at runtime and validates `scope` values against it. If the taxonomy file contains values, any guardrail with an unrecognised scope is rejected with exit code 20 (`validation_error`). If the `scope` array is empty, all values are accepted (free-form mode).

---

## 7. Embedding Model

### 7.1 Choice: Model2Vec (potion-base-8M)

Model2Vec produces static, uncontextualized embeddings. The same input always produces the exact same vector — fully deterministic, consistent with the tool's philosophy.

| Property | Value |
|----------|-------|
| Model | `minishlab/potion-base-8M` |
| Dimensions | 256 |
| Model size on disk | ~8 MB |
| Dependencies | `numpy` (base package only) |
| Inference speed | ~500x faster than sentence-transformers on CPU |
| Embedding type | Static (uncontextualized) |

### 7.2 Bundled in Repository

At ~8 MB, the model is committed directly to the Git repository under `guardrails/models/potion-base-8M/`. This ensures:

- Every team member gets the exact same embeddings. No model version drift.
- No external network access (HuggingFace) is required after initial setup.
- The model is version-controlled alongside the guardrails data.
- The embedding model ships as a committed artifact. `guardrails init` creates the
  repository files; index and embedding warm-up happen lazily on the first add/search/build.

### 7.3 Embedding Strategy

On build, the CLI concatenates `title + " " + guidance + " " + rationale` for each guardrail and computes a single embedding vector. Vectors are stored as float32 BLOBs in the SQLite database. At the scale of hundreds of guardrails, brute-force cosine similarity is sub-millisecond — no ANN index needed.

### 7.4 Model Upgrade Path

If the team decides to upgrade the model:

1. Replace the model directory in `guardrails/models/`.
2. Run `guardrails build --force` to recompute all embeddings.
3. Commit the new model and rebuilt JSONL (embeddings are not stored in JSONL — they are derived state in SQLite).

---

## 8. Workflows

### 8.1 Ingestion (Primary Workflow)

The agent reads a policy document, standard, or architectural review output. It extracts candidate guardrails with citations. The CLI interaction pattern:

```
1. Agent: guardrails search "managed services cloud hosting"
   → CLI returns ranked matches (FTS5 + vector hybrid)
   → Agent decides: new guardrail or update existing?

2a. If new:
   Agent: guardrails add < guardrail.json
   → CLI validates, appends to JSONL, rebuilds index, returns created record

2b. If existing:
   Agent: guardrails update <id> < patch.json
   → CLI applies patch, rewrites JSONL line, rebuilds index
   Agent: guardrails ref-add <id> < ref.json
   → CLI appends reference, rebuilds index
```

The `add` command accepts a complete guardrail-with-references as a single JSON blob on stdin, minimizing round-trips. The `update` command supports **patch semantics** — the agent sends only changed fields.

Authoring guardrail status policy:

- Prefer `draft` when authority is incomplete, key fields are inferred/defaulted, or no evidence excerpt is available.
- Only use `active` when the rule is clearly supported by an authoritative source, at least one attached reference includes an evidence-bearing `excerpt`, and the guardrail has a non-placeholder owner.

### 8.2 Governance Consultation

Someone is making an architectural decision and needs to know what guardrails apply:

```
1. Agent: guardrails search "event streaming messaging" --scope it-platform --status active
   → CLI returns ranked summaries (title, severity, snippet, score)

2. Agent: guardrails get <id>
   → CLI returns full guardrail detail with references and links

3. Agent: guardrails related <id>
   → CLI returns linked guardrails (supports, conflicts, refines)
```

Search returns compact summaries for triage; `get` returns full detail for reasoning.

### 8.3 Structured Validation

The agent assembles a context document describing a proposed decision:

```json
{
  "decision": "Adopt self-hosted Apache Kafka for payments event streaming",
  "domain": "payments",
  "scope": ["it-platform", "channels"],
  "applies_to": ["technology", "platform"],
  "lifecycle_stage": "acquire",
  "tags": ["kafka", "event-streaming", "self-hosted"]
}
```

```
Agent: guardrails check < context.json
→ CLI does deterministic matching: FTS on text fields + filter intersection on structured fields
→ Returns all matching guardrails grouped by severity with match metadata
```

The CLI does not judge compliance. It surfaces what is relevant. The agent reasons about whether the decision violates, complies with, or requires an exception to each guardrail.

### 8.4 Lifecycle and Hygiene

```
Agent: guardrails review-due --before 2026-06-01
→ List guardrails past or approaching review date

Agent: guardrails deprecate <id> --reason "Superseded by cloud-native policy update"
→ Marks guardrail as deprecated

Agent: guardrails supersede <id> --by <new_id>
→ Sets superseded_by on old guardrail, creates link
```

### 8.5 Bootstrapping / Bulk Import

Initial adoption from existing sources:

```
Agent: guardrails import guardrails-export.json
→ Bulk upsert (match on ID or title), validates, rebuilds index

Agent: guardrails deduplicate --threshold 0.85
→ FTS + vector similarity duplicate detection report
→ Agent reviews and decides which to merge
```

---

## 9. Command Surface

### 9.1 Setup Commands

| Command | Description |
|---------|-------------|
| `guardrails init [--taxonomy <file>]` | Create JSONL files, taxonomy, and `.gitignore`. The bundled model is used later during lazy build/search warm-up. Optionally bootstrap scope taxonomy from a JSON file (see §6.8). |
| `guardrails build [--force]` | Rebuild SQLite from JSONL (usually automatic via lazy build) |
| `guardrails validate` | Check JSONL integrity, broken links, orphan refs (CI-friendly) |

### 9.2 Write Commands (Ingestion Workflow)

| Command | Description |
|---------|-------------|
| `guardrails add < guardrail.json` | Add guardrail with inline references. Accepts JSON on stdin. |
| `guardrails update <id> < patch.json` | Partial update with patch semantics (merge, not replace) |
| `guardrails ref-add <id> < ref.json` | Add reference/citation to existing guardrail |
| `guardrails link <from_id> <to_id> --rel <type>` | Create typed relationship between guardrails |
| `guardrails deprecate <id> --reason "..."` | Mark guardrail as deprecated |
| `guardrails supersede <id> --by <new_id>` | Set superseded_by, create "supersedes" link |

### 9.3 Read Commands (Consultation Workflow)

| Command | Description |
|---------|-------------|
| `guardrails search <query> [--filters]` | Hybrid FTS5 + vector search, BM25/RRF ranked |
| `guardrails get <id>` | Full detail including references and links |
| `guardrails related <id>` | Show linked guardrails with relationship types |
| `guardrails list [--filters]` | Filtered listing without full-text search |
| `guardrails check < context.json` | Structured validation against the guardrail corpus |

### 9.4 Export Commands

| Command | Description |
|---------|-------------|
| `guardrails export [--format json\|csv\|markdown] [--filters]` | Filtered export |

### 9.5 Maintenance Commands

| Command | Description |
|---------|-------------|
| `guardrails stats` | Counts by status, severity, scope, staleness |
| `guardrails review-due [--before <date>]` | List guardrails needing review |
| `guardrails deduplicate [--threshold <float>]` | Detect likely duplicates via hybrid similarity |
| `guardrails import <file>` | Bulk upsert from JSON/CSV |

### 9.6 Common Filters

All read and export commands accept these filters, combinable:

| Filter | Example |
|--------|---------|
| `--status` | `--status active` |
| `--severity` | `--severity must` |
| `--scope` | `--scope it-platform` |
| `--applies-to` | `--applies-to application` |
| `--lifecycle-stage` | `--lifecycle-stage acquire` |
| `--owner` | `--owner "Platform Team"` |
| `--review-before` | `--review-before 2026-09-01` |
| `--top` | `--top 10` (for search) |

---

## 10. Search and Retrieval

### 10.1 Hybrid Search Architecture

The `guardrails search` command combines two retrieval methods:

1. **BM25 (FTS5)** — Keyword-based full-text search across title, rationale, guidance, exceptions, and scope fields. Catches exact terminology matches ("Kafka", "API gateway", "PII").

2. **Vector Similarity** — Cosine similarity between query embedding and guardrail embeddings. Catches semantic matches where different terminology describes the same concept ("event-driven architecture" matches "pub/sub patterns").

### 10.2 Reciprocal Rank Fusion (RRF)

Results from both retrieval methods are merged using RRF:

```
RRF_score(d) = Σ 1 / (k + rank_i(d))
```

Where `k` is a constant (default 60) and `rank_i(d)` is the rank of document `d` in retrieval method `i`. Documents appearing high in either list are promoted in the merged result.

### 10.3 Search Output

The search command returns compact summaries for triage:

```json
{
  "results": [
    {
      "id": "01HXR...",
      "title": "Prefer managed services over self-hosted infrastructure",
      "severity": "should",
      "status": "active",
      "score": 0.842,
      "match_sources": ["bm25", "vector"],
      "snippet": "When evaluating infrastructure options, prefer managed..."
    }
  ],
  "total": 4,
  "query": "managed services cloud hosting",
  "filters_applied": {"status": "active", "scope": "it-platform"}
}
```

### 10.4 Check Output

The `check` command returns structured validation results:

```json
{
  "context": {
    "decision": "Adopt self-hosted Apache Kafka...",
    "scope": ["it-platform", "channels"]
  },
  "matches": [
    {
      "id": "01HXR...",
      "title": "Prefer managed services over self-hosted infrastructure",
      "severity": "should",
      "score": 0.842,
      "match_sources": ["bm25", "scope"],
      "match_fields": ["guidance", "scope"]
    }
  ],
  "summary": {
    "must": 1,
    "should": 2,
    "may": 1,
    "total": 4
  }
}
```

---

## 11. CLI Design Principles

This tool conforms to the [Agent-Friendly CLI Manifest](./CLI-MANIFEST.md). Key principles:

### 11.1 Output Discipline

- **stdout**: Structured JSON output only (default for all commands).
- **stderr**: Progress messages, warnings, and diagnostics.
- `--format table` for human-readable output; `--format markdown` for publishing pipelines.
- `--quiet` suppresses stderr noise.

For authoring workflows, `guardrails guide`, `guardrails add --explain`, and `guardrails add --schema` also surface provenance/defaulting guidance so agents can distinguish source-derived facts from inferred metadata.

### 11.2 Progressive Discoverability

| Flag | Purpose |
|------|---------|
| `--help` | Usage and options for any command |
| `--explain` | Natural-language description of what the command does and its contract |
| `--schema` | JSON Schema for the command's output format |

### 11.3 Deterministic Contracts

- All commands produce stable JSON schemas. Schema changes require a version bump.
- Exit codes are stable and documented (see §12).
- The same input always produces the same output (no randomness, no LLM inference).

### 11.4 Stdin for Input

Write commands accept JSON input on stdin, not as command-line arguments. This allows agents to compose complex inputs without shell escaping issues:

```bash
echo '{"title":"...","severity":"must",...}' | guardrails add
cat context.json | guardrails check
```

---

## 12. Error Handling and Exit Codes

### 12.1 Exit Code Reference

| Code | Name | Description |
|------|------|-------------|
| 0 | `success` | Operation completed successfully |
| 1 | `general_error` | General/unspecified error |
| 2 | `usage_error` | Bad arguments, missing required options |
| 10 | `not_found` | Guardrail, reference, or link not found |
| 11 | `already_exists` | Duplicate (same ID or title on add) |
| 12 | `invalid_transition` | Invalid status transition (e.g. supersede a draft) |
| 20 | `validation_error` | Input fails Pydantic validation |
| 21 | `integrity_error` | JSONL integrity check failed (broken links, orphan refs) |
| 30 | `build_error` | SQLite index build failed |
| 31 | `model_error` | Embedding model not found or failed to load |
| 40 | `io_error` | File read/write error |
| 50 | `internal_error` | Bug — should not happen |

### 12.2 Error JSON Format

```json
{
  "ok": false,
  "error": {
    "code": 20,
    "name": "validation_error",
    "message": "Field 'severity' must be one of: must, should, may",
    "details": {
      "field": "severity",
      "value": "critical",
      "allowed": ["must", "should", "may"]
    }
  }
}
```

---

## 13. Export and Publishing

### 13.1 Export Formats

| Format | Use Case |
|--------|----------|
| `json` | Machine consumption, downstream tools |
| `csv` | Spreadsheet import via `xl-agent-cli` |
| `markdown` | Confluence publishing via `confpub-cli` |

### 13.2 Publishing Pipeline

The agent orchestrates a deterministic pipeline using existing EA toolbox CLIs:

```bash
# Publish active guardrails to Confluence
guardrails export --status active --format markdown > guardrails-catalog.md
confpub publish guardrails-catalog.md --space EA --title "Architecture Guardrails"

# Generate governance tracker spreadsheet
guardrails export --format csv > guardrails-tracker.csv
xl-agent-cli create guardrails-report.xlsx --from guardrails-tracker.csv
```

### 13.3 Markdown Export Structure

The markdown export produces a Confluence-ready document with:

- Summary table (counts by status and severity)
- Guardrails grouped by scope, sorted by severity (must → should → may)
- Each guardrail as a section with title, guidance, rationale, exceptions, references
- Review dates highlighted for guardrails approaching or past review

---

## 14. CI/CD Integration

### 14.1 GitHub Actions: Validation

Run on every PR that touches `guardrails/`:

```yaml
name: Guardrails Validation
on:
  pull_request:
    paths: ['guardrails/**']
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv tool install guardrails-cli
      - run: guardrails validate
      - run: guardrails build
      - run: guardrails stats --format json
```

### 14.2 Git Hooks

Optional `post-checkout` / `post-merge` hook:

```bash
#!/bin/sh
guardrails build --quiet
```

### 14.3 PR Diff Example

A PR adding a new guardrail shows:

```diff
# guardrails/guardrails.jsonl
+ {"id":"01J5K...","title":"All APIs must be registered in the API catalog","status":"draft","severity":"must",...}

# guardrails/references.jsonl
+ {"guardrail_id":"01J5K...","ref_type":"policy","ref_id":"POL-API-001","ref_title":"API Governance Policy v2.1","ref_url":"https://..."}
```

That is a reviewable governance change.

---

## 15. Implementation Stack

| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|
| Runtime | Python | 3.12+ | Broad ecosystem, native `tomllib` |
| Package Manager | uv | 0.5+ | Fast, reproducible, `uv tool install` |
| CLI Framework | Typer | 0.12+ | Rich integration, type-safe |
| Validation | Pydantic v2 | 2.0+ | Fast (Rust core), JSON Schema generation |
| Database | SQLite | 3.45+ | WAL mode, FTS5, zero setup |
| Embeddings | Model2Vec | latest | numpy-only, static, deterministic |
| Human Output | Rich | 13.0+ | Tables, panels, progress bars |
| JSON Serialization | orjson | 3.9+ | Fast serialization to stdout |
| IDs | python-ulid | latest | Sortable, timestamp-embedded |
| Type Checking | pyright | strict | Catches errors at development time |
| Linting | ruff | 0.4+ | Fast, replaces black + isort + flake8 |
| Testing | pytest + hypothesis | latest | Property-based testing for data integrity |

---

## 16. Project Structure

```
guardrails-cli/
├── pyproject.toml              # uv project, [project.scripts] entry point
├── README.md
├── LICENSE
├── src/
│   └── guardrails_cli/
│       ├── __init__.py
│       ├── __main__.py         # Entry point
│       ├── cli/                # Typer command definitions
│       │   ├── __init__.py     # Main app + global options
│       │   ├── setup.py        # init, build, validate
│       │   ├── write.py        # add, update, ref_add, link, deprecate, supersede
│       │   ├── read.py         # search, get, related, list, check
│       │   ├── export.py       # export
│       │   └── maintenance.py  # stats, review_due, deduplicate, import
│       ├── core/               # Business logic
│       │   ├── models.py       # Pydantic models
│       │   ├── store.py        # JSONL read/write operations
│       │   ├── index.py        # SQLite index build + queries
│       │   ├── search.py       # Hybrid search (BM25 + vector + RRF)
│       │   ├── embeddings.py   # Model2Vec wrapper
│       │   └── validator.py    # Integrity checks
│       └── output/             # Output formatting
│           ├── json.py         # orjson serialization
│           ├── table.py        # Rich table output
│           └── markdown.py     # Markdown export
└── tests/
    ├── conftest.py             # Shared fixtures, temp JSONL files
    ├── test_models.py          # Pydantic model validation
    ├── test_store.py           # JSONL read/write
    ├── test_index.py           # SQLite index build + query
    ├── test_search.py          # Hybrid search accuracy
    ├── test_cli.py             # CLI integration tests (typer.testing.CliRunner)
    └── test_properties.py      # Hypothesis property-based tests
```

---

## 17. Pydantic Models

### 17.1 Core Models

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

class Guardrail(BaseModel):
    id: str = Field(description="ULID identifier")
    title: str = Field(min_length=1, max_length=200)
    status: Literal["draft", "active", "deprecated", "superseded"]
    severity: Literal["must", "should", "may"]
    rationale: str = Field(min_length=1)
    guidance: str = Field(min_length=1)
    exceptions: str = Field(default="")
    consequences: str = Field(default="")
    scope: list[str] = Field(min_length=1, description="Validated against taxonomy.json at runtime")
    applies_to: list[str] = Field(min_length=1)
    lifecycle_stage: list[str] = Field(default=["acquire", "build", "operate", "retire"])
    owner: str = Field(min_length=1)
    review_date: str | None = Field(default=None, description="ISO 8601 date")
    superseded_by: str | None = Field(default=None)
    created_at: str = Field(description="ISO 8601 datetime")
    updated_at: str = Field(description="ISO 8601 datetime")
    metadata: dict = Field(default_factory=dict)

class Reference(BaseModel):
    guardrail_id: str
    ref_type: Literal["adr", "policy", "standard", "regulation", "pattern", "document"]
    ref_id: str
    ref_title: str
    ref_url: str | None = None
    excerpt: str = ""
    added_at: str

class Link(BaseModel):
    from_id: str
    to_id: str
    rel_type: Literal["supports", "conflicts", "refines", "implements"]
    note: str = ""
```

### 17.2 Input Models (Patch Semantics)

```python
class GuardrailPatch(BaseModel):
    """Partial update — only provided fields are applied."""
    title: str | None = None
    status: Literal["draft", "active", "deprecated", "superseded"] | None = None
    severity: Literal["must", "should", "may"] | None = None
    rationale: str | None = None
    guidance: str | None = None
    exceptions: str | None = None
    consequences: str | None = None
    scope: list[str] | None = None
    applies_to: list[str] | None = None
    lifecycle_stage: list[str] | None = None
    owner: str | None = None
    review_date: str | None = None
    metadata: dict | None = None
```

### 17.3 Output Models

```python
class SearchResult(BaseModel):
    id: str
    title: str
    severity: Literal["must", "should", "may"]
    status: str
    score: float
    match_sources: list[Literal["bm25", "vector"]]
    snippet: str

class SearchResponse(BaseModel):
    ok: bool = True
    results: list[SearchResult]
    total: int
    query: str
    filters_applied: dict

class CheckResponse(BaseModel):
    ok: bool = True
    context: dict
    matches: list[SearchResult]
    summary: dict  # {"must": int, "should": int, "may": int, "total": int}

class ErrorResponse(BaseModel):
    ok: bool = False
    error: dict  # {"code": int, "name": str, "message": str, "details": dict}
```

---

## 18. Acceptance Criteria

### 18.1 Functional

- [ ] `guardrails init` creates JSONL files, `taxonomy.json`, and `.gitignore`.
- [ ] The bundled embedding model is available without network access and is loaded during lazy build/search warm-up.
- [ ] `guardrails init --taxonomy <file>` bootstraps scope vocabulary from an external JSON file.
- [ ] `guardrails add` accepts a guardrail JSON on stdin, validates it, appends to JSONL, rebuilds index, and returns the created record.
- [ ] `guardrails search` returns ranked results using hybrid BM25 + vector search with RRF fusion.
- [ ] `guardrails check` accepts a context JSON on stdin and returns matching guardrails grouped by severity.
- [ ] `guardrails export --format markdown` produces a Confluence-ready guardrails catalog.
- [ ] `guardrails validate` exits 0 for valid JSONL, non-zero with details for invalid data.
- [ ] All write commands correctly update JSONL and rebuild the SQLite index.
- [ ] Lazy auto-build triggers when JSONL is newer than the SQLite database.

### 18.2 Agent Ergonomics

- [ ] All commands default to `--format json` with structured, parseable output on stdout.
- [ ] All commands support `--help`, `--explain`, and `--schema`.
- [ ] Exit codes are stable and match §12.
- [ ] Errors are returned as structured JSON (§12.2), never unstructured text on stdout.
- [ ] stdin input for write commands avoids shell escaping issues.

### 18.3 Git Workflow

- [ ] The `.guardrails.db` file is gitignored and never committed.
- [ ] The embedding model is committed and functional without network access.
- [ ] JSONL diffs in PRs are clean, readable, and per-guardrail.
- [ ] `guardrails validate` runs successfully in GitHub Actions CI.

### 18.4 Performance

- [ ] `guardrails build` completes in under 5 seconds for 500 guardrails.
- [ ] `guardrails search` returns results in under 200ms for 500 guardrails.
- [ ] CLI startup time is under 200ms.

---

## 19. MVP Milestones

### M1: Core Store (Week 1-2)

- `init`, `build`, `validate`
- `add`, `get`, `list`
- JSONL read/write with Pydantic validation
- SQLite index build with FTS5
- JSON output formatting

### M2: Search and Retrieval (Week 3)

- `search` with BM25 (FTS5)
- Model2Vec integration and vector search
- Hybrid RRF fusion
- `check` command

### M3: Relationships and Lifecycle (Week 4)

- `update` (patch semantics), `ref-add`, `link`
- `related`, `deprecate`, `supersede`
- `review-due`, `stats`

### M4: Export, Import, Polish (Week 5)

- `export` (JSON, CSV, Markdown)
- `import` (bulk upsert)
- `deduplicate`
- CI/CD examples
- Documentation and README

---

## 20. Resolved Design Decisions

1. **Scope vocabulary**: Configurable taxonomy loaded from `taxonomy.json` during `guardrails init --taxonomy <file>` (see §6.8). Scope values are validated at runtime against the taxonomy. If the taxonomy is empty, scope values are free-form. The taxonomy file is committed to Git and versioned alongside the guardrails data.

2. **Multi-language support**: English only. FTS5 uses the `unicode61` tokenizer optimised for English content. No multi-language support is required.

3. **Versioning within guardrails**: No in-record version tracking. Git history is the audit trail for all guardrail changes. The `updated_at` timestamp records when the current version was last modified.

4. **Integration with other toolbox CLIs**: No first-class integration with `bcm-cli` or other toolbox CLIs. Cross-tool orchestration (e.g., mapping guardrails to business capabilities) is the responsibility of the agent.

5. **Model size**: `potion-base-8M` (~8 MB) is the default. The small footprint is appropriate for commit-to-repo deployment and sufficient for the scale of a guardrails corpus.

---

*This PRD is a living document. It will be updated as the team iterates on the design.*
