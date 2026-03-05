"""Setup commands: init, build, validate."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from archguard.cli import app, state
from archguard.output.json import success_response

# TODO: Wire up core.store and core.index once implemented


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
    """Create guardrails data directory, JSONL files, taxonomy, and download embedding model."""
    if explain:
        sys.stdout.write(
            "init creates the guardrails/ data directory with empty JSONL files, "
            "a taxonomy.json, a .gitignore, and downloads the embedding model.\n"
        )
        raise SystemExit(0)

    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create empty JSONL files
    for fname in ("guardrails.jsonl", "references.jsonl", "links.jsonl"):
        fpath = data_dir / fname
        if not fpath.exists():
            fpath.touch()

    # Create taxonomy
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

    # TODO: Download and store potion-base-8M model under data_dir/models/
    # For now, create the directory structure
    models_dir = data_dir / "models" / "potion-base-8M"
    models_dir.mkdir(parents=True, exist_ok=True)

    sys.stdout.write(
        success_response({"message": "Initialized guardrails repository", "path": str(data_dir)})
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
        sys.stdout.write(
            "build reads all JSONL files, validates them, creates the SQLite FTS5 index, "
            "and computes embedding vectors for semantic search.\n"
        )
        raise SystemExit(0)

    from archguard.core.index import build_index
    from archguard.core.store import load_guardrails, load_links, load_references

    data_dir = Path(state.data_dir)
    db_path = data_dir / ".guardrails.db"

    guardrails_list = load_guardrails(data_dir)
    refs_list = load_references(data_dir)
    links_list = load_links(data_dir)

    # Attempt to compute embeddings if model is available
    embeddings: dict[str, bytes] | None = None
    embedding_count = 0
    model_dir = data_dir / "models" / "potion-base-8M"
    try:
        from archguard.core.embeddings import embed_guardrail, embedding_to_blob, load_model

        model = load_model(model_dir)
        embeddings = {}
        for g in guardrails_list:
            vec = embed_guardrail(model, g)
            embeddings[g.id] = embedding_to_blob(vec)
        embedding_count = len(embeddings)
    except Exception:
        embeddings = None

    build_index(db_path, guardrails_list, refs_list, links_list, embeddings=embeddings)

    sys.stdout.write(
        success_response(
            {
                "message": "Index built successfully",
                "guardrails": len(guardrails_list),
                "references": len(refs_list),
                "links": len(links_list),
                "embeddings": embedding_count,
            }
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
        sys.stdout.write(
            "validate checks that all JSONL files parse correctly, all references point to "
            "existing guardrails, all links connect existing guardrails, and all scope values "
            "match the taxonomy.\n"
        )
        raise SystemExit(0)

    from archguard.core.validator import validate_corpus

    data_dir = Path(state.data_dir)
    result = validate_corpus(data_dir)

    if result.ok:
        sys.stdout.write(
            success_response({"errors": [], "warnings": result.warnings}) + "\n"
        )
    else:
        import orjson

        sys.stdout.write(
            orjson.dumps(
                {"ok": False, "errors": result.errors, "warnings": result.warnings}
            ).decode()
            + "\n"
        )
        raise SystemExit(21)
