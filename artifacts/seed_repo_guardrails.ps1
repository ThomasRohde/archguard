$ErrorActionPreference = 'Stop'

function Invoke-Archguard {
    param(
        [string[]]$CommandArgs,
        [string]$InputText = $null
    )

    if ($null -ne $InputText) {
        $output = $InputText | uv run archguard @CommandArgs
    }
    else {
        $output = uv run archguard @CommandArgs
    }

    if ($LASTEXITCODE -ne 0) {
        throw "archguard command failed: archguard $($CommandArgs -join ' ')"
    }

    return $output
}

$taxonomyPath = Join-Path $env:TEMP 'archguard-repo-taxonomy.json'
$taxonomy = @{
    scope = @(
        'storage-architecture',
        'runtime-architecture',
        'cli-contract',
        'data-model',
        'agent-experience',
        'lifecycle-governance',
        'quality-gates'
    )
} | ConvertTo-Json -Depth 3
Set-Content -Path $taxonomyPath -Value $taxonomy -Encoding utf8

if (Test-Path 'artifacts/repo-guardrails') {
    Remove-Item 'artifacts/repo-guardrails' -Recurse -Force
}
if (Test-Path 'docs/repo-guardrails.md') {
    Remove-Item 'docs/repo-guardrails.md' -Force
}

Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'init', '--taxonomy', $taxonomyPath) | Out-Null

$guardrails = @(
    @{
        title = 'Keep JSONL as the source of truth and rebuild SQLite as derived state'
        status = 'active'
        severity = 'must'
        rationale = 'The repository depends on reviewable JSONL data and a rebuildable SQLite index to preserve Git-friendly diffs and deterministic rebuilds.'
        guidance = 'Keep authoritative corpus data in JSONL files only. Treat SQLite as a derived artifact, rebuild it from JSONL after writes, and never make SQLite-only changes the source of record.'
        exceptions = ''
        consequences = 'Direct SQLite-only edits create drift, break reviewability, and undermine the repository contract.'
        scope = @('storage-architecture')
        applies_to = @('storage', 'indexing', 'repository')
        lifecycle_stage = @('build', 'operate')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'PRD-6.1'
                ref_title = 'PRD.md Section 6.1 Design Principle: JSONL is Source, SQLite is Index'
                ref_url = 'PRD.md#61-design-principle-jsonl-is-source-sqlite-is-index'
                excerpt = 'JSONL files are the source of truth. SQLite is a derived runtime artifact.'
            },
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-ARCH-1'
                ref_title = 'AGENTS.md Architectural invariants'
                ref_url = 'AGENTS.md'
                excerpt = 'JSONL files are the source of truth; SQLite is derived'
            }
        )
    },
    @{
        title = 'Keep the CLI deterministic and free of LLM inference'
        status = 'active'
        severity = 'must'
        rationale = 'The tool is designed as a deterministic governance system whose behavior must not depend on model calls at runtime.'
        guidance = 'Do not implement LLM inference inside the CLI. Keep behavior deterministic so the same input produces the same output and agents provide reasoning outside the tool.'
        exceptions = ''
        consequences = 'Embedding inference into the CLI would break determinism, complicate testing, and violate the published tool contract.'
        scope = @('runtime-architecture', 'agent-experience')
        applies_to = @('cli', 'reasoning', 'runtime')
        lifecycle_stage = @('build', 'operate')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'PRD-3.1'
                ref_title = 'PRD.md Non-Goals'
                ref_url = 'PRD.md#3-non-goals'
                excerpt = 'No LLM inference inside the CLI. The tool is deterministic. The agent provides the intelligence.'
            },
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-ARCH-2'
                ref_title = 'AGENTS.md Architectural invariants'
                ref_url = 'AGENTS.md'
                excerpt = 'No LLM inference inside the CLI'
            }
        )
    },
    @{
        title = 'Emit structured JSON on stdout and reserve stderr for diagnostics'
        status = 'active'
        severity = 'must'
        rationale = 'Agent automation depends on a stable response envelope and predictable separation of machine-readable output from human diagnostics.'
        guidance = 'Emit structured JSON on stdout for command results and errors. Write progress and diagnostics to stderr, and keep command responses aligned with the published envelope and exit-code contract.'
        exceptions = ''
        consequences = 'Mixing prose with result data makes automation fragile and breaks the agent-first CLI contract.'
        scope = @('cli-contract')
        applies_to = @('cli', 'output', 'automation')
        lifecycle_stage = @('build', 'operate')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-CODE-1'
                ref_title = 'AGENTS.md Coding rules'
                ref_url = 'AGENTS.md'
                excerpt = 'stdout: structured JSON only (default). stderr: diagnostics.'
            },
            @{
                ref_type = 'document'
                ref_id = 'CLI-MANIFEST-1'
                ref_title = 'CLI-MANIFEST.md Part I Foundations'
                ref_url = 'CLI-MANIFEST.md#1-every-command-returns-a-structured-envelope'
                excerpt = 'Every command - success or failure - returns the same top-level JSON shape.'
            }
        )
    },
    @{
        title = 'Validate data with Pydantic and serialize JSON with orjson'
        status = 'active'
        severity = 'must'
        rationale = 'The project standardizes validation and serialization choices so schemas, performance, and behavior stay consistent across the CLI.'
        guidance = 'Use Pydantic v2 for all data validation and use orjson for JSON serialization. Avoid ad hoc dict validation and avoid falling back to the standard json module in core CLI flows.'
        exceptions = ''
        consequences = 'Mixing validation and serialization approaches increases schema drift and weakens the codebase contract.'
        scope = @('data-model')
        applies_to = @('python-module', 'validation', 'serialization')
        lifecycle_stage = @('build')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-CODE-2'
                ref_title = 'AGENTS.md Coding rules'
                ref_url = 'AGENTS.md'
                excerpt = 'Use Pydantic v2 for all data validation'
            },
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-CODE-3'
                ref_title = 'AGENTS.md Coding rules'
                ref_url = 'AGENTS.md'
                excerpt = 'Use orjson for JSON serialization (not stdlib json)'
            }
        )
    },
    @{
        title = 'Read write-command payloads from stdin and expose explainable contracts'
        status = 'active'
        severity = 'must'
        rationale = 'Agents need stable input channels and discoverable contracts so they can compose requests without shell-escaping games or external documentation.'
        guidance = 'Use stdin for all write-command JSON payloads. Support --explain on all commands. Provide --schema on add and check so agents can bootstrap usage from the CLI itself.'
        exceptions = ''
        consequences = 'Moving structured inputs into ad hoc flags or undocumented side channels makes agent automation brittle.'
        scope = @('cli-contract', 'agent-experience')
        applies_to = @('cli', 'authoring', 'automation')
        lifecycle_stage = @('build', 'operate')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-CODE-4'
                ref_title = 'AGENTS.md Coding rules'
                ref_url = 'AGENTS.md'
                excerpt = 'All write commands read JSON from stdin'
            },
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-CODE-5'
                ref_title = 'AGENTS.md Coding rules'
                ref_url = 'AGENTS.md'
                excerpt = 'All commands support --explain; add and check support --schema'
            }
        )
    },
    @{
        title = 'Prefer deprecate or supersede workflows over destructive deletion'
        status = 'active'
        severity = 'should'
        rationale = 'Governance records benefit from an audit trail, so retirement should usually preserve history rather than erase it.'
        guidance = 'Prefer deprecate or supersede workflows when replacing or retiring a guardrail. Use delete only for exceptional cleanup scenarios and require explicit confirmation before destructive removal.'
        exceptions = 'Deletion is reserved for deliberate repository cleanup with explicit confirmation and documented intent.'
        consequences = 'Overusing deletion removes historical context and weakens traceability for governance decisions.'
        scope = @('lifecycle-governance')
        applies_to = @('guardrail-record', 'cli', 'lifecycle')
        lifecycle_stage = @('operate', 'retire')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-ARCH-3'
                ref_title = 'AGENTS.md Architectural invariants'
                ref_url = 'AGENTS.md'
                excerpt = 'Prefer deprecate/supersede over delete; delete exists but requires --confirm'
            },
            @{
                ref_type = 'document'
                ref_id = 'PRD-3.4'
                ref_title = 'PRD.md Non-Goals'
                ref_url = 'PRD.md#3-non-goals'
                excerpt = 'Guardrails are deprecated or superseded, never deleted. The governance audit trail matters.'
            }
        )
    },
    @{
        title = 'Gate changes with tests, lint, and type checking'
        status = 'active'
        severity = 'must'
        rationale = 'The project relies on automated validation to keep CLI behavior, schemas, and implementation quality aligned as the codebase evolves.'
        guidance = 'Run pytest, Ruff, and Pyright for every pull request. Add corresponding tests for new functionality and validate model or JSONL changes with the appropriate focused coverage.'
        exceptions = ''
        consequences = 'Skipping validation increases the risk of regressions in the CLI contract, schemas, and repository invariants.'
        scope = @('quality-gates')
        applies_to = @('testing', 'linting', 'type-checking', 'pull-request')
        lifecycle_stage = @('build')
        owner = 'EA Team'
        metadata = @{ source_domain = 'archguard-repo' }
        references = @(
            @{
                ref_type = 'document'
                ref_id = 'TESTING-PR-1'
                ref_title = 'TESTING.md What must be tested for each PR'
                ref_url = 'TESTING.md'
                excerpt = 'All existing tests pass (uv run pytest)'
            },
            @{
                ref_type = 'document'
                ref_id = 'AGENTS-VALIDATE-1'
                ref_title = 'AGENTS.md How to run validation'
                ref_url = 'AGENTS.md'
                excerpt = 'uv run pytest; uv run ruff check src/ tests/; uv run pyright src/'
            }
        )
    }
)

foreach ($guardrail in $guardrails) {
    $json = $guardrail | ConvertTo-Json -Depth 8 -Compress
    Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'add') -InputText $json | Out-Null
}

$links = @(
    @{
        from = 'gr-0001'
        to = 'gr-0003'
        rel = 'supports'
        note = 'Derived indexing and maintenance flows depend on stable machine-readable command output.'
    },
    @{
        from = 'gr-0002'
        to = 'gr-0003'
        rel = 'supports'
        note = 'Deterministic runtime behavior reinforces the structured CLI contract.'
    },
    @{
        from = 'gr-0004'
        to = 'gr-0003'
        rel = 'implements'
        note = 'Pydantic validation and orjson serialization make the published envelope concrete.'
    },
    @{
        from = 'gr-0005'
        to = 'gr-0003'
        rel = 'supports'
        note = 'Explainable stdin-driven workflows complement machine-readable command responses.'
    },
    @{
        from = 'gr-0007'
        to = 'gr-0004'
        rel = 'requires'
        note = 'Quality gates must exercise the shared validation and serialization contract.'
    },
    @{
        from = 'gr-0006'
        to = 'gr-0001'
        rel = 'supports'
        note = 'Preserving history complements the repository source-of-truth model.'
    }
)

foreach ($link in $links) {
    Invoke-Archguard -CommandArgs @(
        '--data-dir',
        'artifacts/repo-guardrails',
        'link',
        $link.from,
        $link.to,
        '--rel',
        $link.rel,
        '--note',
        $link.note
    ) | Out-Null
}

$validate = Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'validate')
$stats = Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'stats')
$list = Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'list')
$getPublic = Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'get', 'gr-0001')
$markdownOutput = Invoke-Archguard -CommandArgs @('--data-dir', 'artifacts/repo-guardrails', 'export', '--format', 'markdown')
try {
    $markdownEnvelope = $markdownOutput | ConvertFrom-Json -AsHashtable
    if ($markdownEnvelope.result.content) {
        $markdown = [string]$markdownEnvelope.result.content
    }
    else {
        $markdown = [string]$markdownOutput
    }
}
catch {
    $markdown = [string]$markdownOutput
}
Set-Content -Path 'docs/repo-guardrails.md' -Value $markdown -Encoding utf8

'VALIDATE:'
$validate
''
'STATS:'
$stats
''
'LIST:'
$list
''
'GET gr-0001:'
$getPublic
''
'MARKDOWN_EXPORT: docs/repo-guardrails.md'
