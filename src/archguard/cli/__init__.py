"""Typer CLI application definition with global options and LLM mode support."""

from __future__ import annotations

import sys
from typing import Annotated, Any, NoReturn

import click
import typer
from typer.core import TyperGroup

from archguard.output.json import (
    error_envelope,
    exit_code_for,
    init_request,
    is_interactive,
    is_llm_mode,
)


class _FlexibleGroup(TyperGroup):
    """Allow global options (--format, --quiet, --data-dir) after the subcommand."""

    _VALUE_OPTS = frozenset(("--format", "-f", "--data-dir", "-d"))
    _FLAG_OPTS = frozenset(("--quiet", "-q", "--version", "-V"))
    _VALUE_PREFIXES = ("--format=", "--data-dir=")

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # Find the subcommand (first non-option argument)
        cmd_idx: int | None = None
        i = 0
        while i < len(args):
            a = args[i]
            if not a.startswith("-"):
                cmd_idx = i
                break
            if a in self._VALUE_OPTS:
                i += 2
                continue
            if a.startswith(self._VALUE_PREFIXES):
                i += 1
                continue
            i += 1

        if cmd_idx is None:
            return super().parse_args(ctx, args)

        before = list(args[:cmd_idx])
        cmd_and_after = list(args[cmd_idx:])

        # Discover which options the subcommand itself defines,
        # so we don't steal them (e.g. export has its own --format).
        cmd_name = cmd_and_after[0]
        sub_cmd = self.commands.get(cmd_name) if self.commands else None
        sub_opts: set[str] = set()
        if sub_cmd:
            for param in sub_cmd.params:
                sub_opts.update(param.opts)
                sub_opts.update(getattr(param, "secondary_opts", []))

        # Move global options from after subcommand to before it
        moved: list[str] = []
        kept: list[str] = [cmd_and_after[0]]  # subcommand name
        i = 1
        end_of_opts = False
        while i < len(cmd_and_after):
            a = cmd_and_after[i]
            if a == "--":
                end_of_opts = True
                kept.append(a)
                i += 1
                continue
            if not end_of_opts and a in self._VALUE_OPTS and a not in sub_opts:
                moved.append(a)
                if i + 1 < len(cmd_and_after):
                    i += 1
                    moved.append(cmd_and_after[i])
                i += 1
                continue
            if not end_of_opts and a in self._FLAG_OPTS and a not in sub_opts:
                moved.append(a)
                i += 1
                continue
            if (
                not end_of_opts
                and a.startswith(self._VALUE_PREFIXES)
                and not any(a.startswith(f"{o}=") for o in sub_opts)
            ):
                moved.append(a)
                i += 1
                continue
            kept.append(a)
            i += 1

        return super().parse_args(ctx, before + moved + kept)


app = typer.Typer(
    name="archguard",
    cls=_FlexibleGroup,
    help=(
        "Architecture guardrails management CLI.\n\n"
        "Guardrails are the constraints, standards, and rules that govern how systems "
        "are designed, built, and integrated. This CLI provides a single, queryable store "
        "backed by hybrid BM25 + vector search so AI agents and human architects can ask "
        '"what rules apply to this decision?" and get ranked, relevant answers.\n\n'
        "Data lives in Git-friendly JSONL files. The CLI is deterministic — no LLM "
        "inference, no cloud sync. Agents provide the intelligence; this tool provides "
        "the governance knowledge.\n\n"
        "AGENTS: Call 'archguard guide' first. It returns the full CLI schema, "
        "field semantics, capture workflow, quality criteria, and examples. "
        "Before creating a guardrail, call 'archguard search <topic>' to detect "
        "duplicates, then 'archguard add --schema' to fetch the exact input contract. "
        "Prefer status=draft when source authority is uncertain.\n\n"
        "Quick start:\n\n"
        "  archguard guide         Full CLI schema for agent bootstrap\n"
        "  archguard init          Create data directory and taxonomy\n"
        "  archguard add < g.json  Add a guardrail from JSON on stdin\n"
        "  archguard search 'api'  Search guardrails by keyword\n"
        "  archguard check < d.json  Check a decision against the corpus\n"
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
