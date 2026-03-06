"""Typer CLI application definition with global options and LLM mode support."""

from __future__ import annotations

import sys
from typing import Annotated, Any, NoReturn

import typer

from archguard.output.json import (
    error_envelope,
    exit_code_for,
    init_request,
    is_interactive,
    is_llm_mode,
)

app = typer.Typer(
    name="guardrails",
    help=(
        "Architecture guardrails management CLI.\n\n"
        "Guardrails are the constraints, standards, and rules that govern how systems "
        "are designed, built, and integrated. This CLI provides a single, queryable store "
        "backed by hybrid BM25 + vector search so AI agents and human architects can ask "
        '"what rules apply to this decision?" and get ranked, relevant answers.\n\n'
        "Data lives in Git-friendly JSONL files. The CLI is deterministic — no LLM "
        "inference, no cloud sync. Agents provide the intelligence; this tool provides "
        "the governance knowledge.\n\n"
        "Quick start:\n\n"
        "  guardrails init          Create data directory and taxonomy\n"
        "  guardrails add < g.json  Add a guardrail from JSON on stdin\n"
        "  guardrails search 'api'  Search guardrails by keyword\n"
        "  guardrails check < d.json  Check a decision against the corpus\n"
        "  guardrails guide         Full CLI schema for agent bootstrap\n"
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


class GlobalState:
    """Shared state set by global callback options."""

    format: str = "json"
    quiet: bool = False
    data_dir: str = "guardrails"


state = GlobalState()


def _version_callback(value: bool) -> None:
    if value:
        from archguard import __version__

        print(f"archguard {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json, table, markdown"),
    ] = "json",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr progress messages"),
    ] = False,
    data_dir: Annotated[
        str,
        typer.Option("--data-dir", "-d", help="Path to guardrails data directory"),
    ] = "guardrails",
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Architecture guardrails management CLI."""
    # Per-invocation request context (request_id, timing)
    init_request()

    state.data_dir = data_dir

    # Output-mode precedence (CLI-MANIFEST §8):
    #   1. Explicit CLI flags (highest)
    #   2. Environment variables (LLM=true)
    #   3. isatty() defaults
    #
    # Quiet follows: explicit --quiet flag > LLM=true > isatty()
    if format != "json":
        # Explicit format flag takes precedence
        state.format = format
    elif is_llm_mode() or not is_interactive():
        state.format = "json"
    else:
        state.format = format

    # Quiet: explicit flag wins, then LLM/pipe detection
    if quiet or is_llm_mode() or not is_interactive():
        state.quiet = True
    else:
        state.quiet = False


def handle_error(
    command: str, code: str, message: str, details: dict[str, Any] | None = None
) -> NoReturn:
    """Print structured error envelope to stdout and exit with the mapped exit code."""
    output = error_envelope(command, code, message, details)
    sys.stdout.write(output + "\n")
    raise SystemExit(exit_code_for(code))


# Import and register sub-command modules (side-effect imports)
from archguard.cli import export as export  # noqa: E402
from archguard.cli import guide as guide  # noqa: E402
from archguard.cli import maintenance as maintenance  # noqa: E402
from archguard.cli import read as read  # noqa: E402
from archguard.cli import setup as setup  # noqa: E402
from archguard.cli import write as write  # noqa: E402
