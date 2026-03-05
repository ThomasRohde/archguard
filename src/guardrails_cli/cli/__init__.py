"""Typer CLI application definition with global options."""

from __future__ import annotations

import sys
from typing import Annotated, NoReturn

import typer

from guardrails_cli.output.json import error_response

app = typer.Typer(
    name="guardrails",
    help="Architecture guardrails management CLI.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


class GlobalState:
    """Shared state set by global callback options."""

    format: str = "json"
    quiet: bool = False
    data_dir: str = "guardrails"


state = GlobalState()


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
) -> None:
    """Architecture guardrails management CLI."""
    state.format = format
    state.quiet = quiet
    state.data_dir = data_dir


def handle_error(code: int, name: str, message: str, details: dict | None = None) -> NoReturn:
    """Print structured error JSON to stdout and exit with the given code."""
    output = error_response(code, name, message, details or {})
    sys.stdout.write(output + "\n")
    raise SystemExit(code)


# Import and register sub-command modules
from guardrails_cli.cli import export, maintenance, read, setup, write  # noqa: E402, F401
