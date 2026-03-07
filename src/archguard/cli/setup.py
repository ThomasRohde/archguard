"""Setup commands: init, build, validate."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from archguard.cli import (
    app,
    emit_index_build_notice,
    ensure_supported_format,
    require_data_dir,
    state,
)
from archguard.output.json import envelope


@app.command()
def init(
    taxonomy: Annotated[
        Path | None,
        typer.Option("--taxonomy", help="JSON file with scope taxonomy to bootstrap"),
    ] = None,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
    schema: Annotated[bool, typer.Option("--schema", help="Print output JSON schema")] = False,
) -> None:
    """Create guardrails data directory, JSONL files, taxonomy, and .gitignore."""
    if explain:
        sys.stderr.write(
            "init creates the guardrails/ data directory with empty JSONL files, "
            "a taxonomy.json, and a .gitignore. Unless --taxonomy is provided, "
            "taxonomy.json starts with an empty scope array, so scope values are "
            "unconstrained until you populate it. The embedding model is bundled "
            "with the package — no download needed. The SQLite index and embeddings "
            "are built lazily on the first add/search/build operation.\n"
        )
        raise SystemExit(0)
    if schema:
        schema_data = {
            "command": "init",
            "output_fields": ["message", "path"],
            "flags": {
                "--taxonomy": "Path to JSON taxonomy file to bootstrap",
                "--data-dir": "Path to guardrails data directory (default: guardrails)",
            },
        }
        sys.stdout.write(envelope("init", {"schema": schema_data}) + "\n")
        raise SystemExit(0)

    ensure_supported_format("init", "json")

    data_dir = Path(state.data_dir)
    already_exists = data_dir.exists()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create empty JSONL files
    for fname in ("guardrails.jsonl", "references.jsonl", "links.jsonl"):
        fpath = data_dir / fname
        if not fpath.exists():
            fpath.touch()

    # Create taxonomy: explicit file > empty default (free-form scope mode)
    if taxonomy and taxonomy.exists():
        import shutil

        shutil.copy(taxonomy, data_dir / "taxonomy.json")
    elif not (data_dir / "taxonomy.json").exists():
        import orjson

        (data_dir / "taxonomy.json").write_bytes(
            orjson.dumps({"scope": []}, option=orjson.OPT_INDENT_2)
        )

    # Create .gitignore for the data directory
    gitignore = data_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".guardrails.db\n")

    warnings: list[str] = []
    if already_exists:
        warnings.append("Data directory already exists; existing data preserved")

    sys.stdout.write(
        envelope(
            "init",
            {"message": "Initialized guardrails repository", "path": str(data_dir)},
            warnings=warnings or None,
        )
        + "\n"
    )


@app.command()
def build(
    force: Annotated[bool, typer.Option("--force", help="Force full rebuild")] = False,
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Rebuild SQLite index from JSONL files."""
    if explain:
        sys.stderr.write(
            "build reads all JSONL files, validates them, creates the SQLite FTS5 index, "
            "and computes embedding vectors for semantic search.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("build", "json")

    from archguard.core.index import build_index
    from archguard.core.store import load_guardrails, load_links, load_references

    data_dir = require_data_dir("build")
    db_path = data_dir / ".guardrails.db"

    emit_index_build_notice("build", data_dir, explicit=True)

    guardrails_list = load_guardrails(data_dir)
    refs_list = load_references(data_dir)
    links_list = load_links(data_dir)

    # Attempt to compute embeddings (bundled model or data-dir override)
    embeddings: dict[str, bytes] | None = None
    embedding_count = 0
    try:
        from archguard.core.embeddings import (
            embed_guardrail,
            embedding_to_blob,
            try_load_model,
        )

        model = try_load_model(data_dir)
        if model is not None:
            embeddings = {}
            for g in guardrails_list:
                vec = embed_guardrail(model, g)
                embeddings[g.id] = embedding_to_blob(vec)
            embedding_count = len(embeddings)
    except Exception:
        embeddings = None

    build_index(db_path, guardrails_list, refs_list, links_list, embeddings=embeddings)

    sys.stdout.write(
        envelope(
            "build",
            {
                "message": "Index built successfully",
                "guardrails": len(guardrails_list),
                "references": len(refs_list),
                "links": len(links_list),
                "embeddings": embedding_count,
            },
        )
        + "\n"
    )


@app.command()
def validate(
    explain: Annotated[
        bool, typer.Option("--explain", help="Explain what this command does")
    ] = False,
) -> None:
    """Check JSONL integrity, broken links, and orphan references."""
    if explain:
        sys.stderr.write(
            "validate checks that all JSONL files parse correctly, all references point to "
            "existing guardrails, all links connect existing guardrails, and all scope values "
            "match the taxonomy.\n"
        )
        raise SystemExit(0)

    ensure_supported_format("validate", "json")

    from archguard.core.validator import validate_corpus
    from archguard.output.json import EXIT_VALIDATION

    data_dir = require_data_dir("validate")
    result = validate_corpus(data_dir)

    if result.ok:
        sys.stdout.write(
            envelope("validate", {"errors": [], "warnings": result.warnings}) + "\n"
        )
    else:
        sys.stdout.write(
            envelope(
                "validate",
                result=None,
                ok=False,
                errors=[{"code": "ERR_VALIDATION", "message": e} for e in result.errors],
                warnings=result.warnings,
            )
            + "\n"
        )
        raise SystemExit(EXIT_VALIDATION)
