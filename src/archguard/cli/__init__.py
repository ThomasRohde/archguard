"""Typer CLI application definition with global options and shared helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn, cast

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
    context_settings={"help_option_names": ["-h", "--help"]},
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
        "Prefer status=draft when source authority is uncertain. Guardrails also receive public "
        "IDs such as gr-0001, and any command that accepts a guardrail identifier accepts either "
        "the public ID or the internal ULID.\n\n"
        "Quick start:\n\n"
        "  archguard guide                  Full CLI schema for agent bootstrap\n"
        "  archguard init                   Create data files and taxonomy\n"
        "  POSIX:      archguard add < g.json\n"
        "  PowerShell: Get-Content .\\g.json | archguard add\n"
        "  archguard search \"api\"          Search guardrails by keyword\n"
        "  POSIX:      archguard check < d.json\n"
        "  PowerShell: Get-Content .\\d.json | archguard check\n"
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
_REPOSITORY_FILES = ("guardrails.jsonl", "references.jsonl", "links.jsonl", "taxonomy.json")


def emit_progress(message: str) -> None:
    """Write a diagnostic message to stderr unless quiet mode is active."""
    if state.quiet:
        return
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()


def emit_index_build_notice(command: str, data_dir: Path, *, explicit: bool = False) -> None:
    """Explain slow first-run index warm-up on interactive terminals."""
    if state.quiet:
        return

    db_exists = (data_dir / ".guardrails.db").exists()
    if explicit:
        emit_progress(
            f"{command}: rebuilding the SQLite index and computing embeddings."
            " First run may take several seconds."
        )
        return

    if not db_exists:
        emit_progress(
            f"{command}: building the search index for first use."
            " Embedding model warm-up may take several seconds."
        )


def require_data_dir(command: str) -> Path:
    """Return the configured data directory after verifying repository initialization."""
    data_dir = Path(state.data_dir)
    if not data_dir.exists():
        handle_error(
            command,
            "ERR_IO_FILE_NOT_FOUND",
            (
                f"Data directory '{data_dir}' does not exist. "
                "Run 'archguard init' for this path before using the repository."
            ),
            details={"path": str(data_dir), "missing": list(_REPOSITORY_FILES)},
        )
    if not data_dir.is_dir():
        handle_error(
            command,
            "ERR_IO_FILE_NOT_FOUND",
            f"Data directory '{data_dir}' is not a directory",
            details={"path": str(data_dir)},
        )

    missing_files = [name for name in _REPOSITORY_FILES if not (data_dir / name).exists()]
    if missing_files:
        handle_error(
            command,
            "ERR_IO_FILE_NOT_FOUND",
            (
                f"Data directory '{data_dir}' is not initialized. "
                "Run 'archguard init' for this path before using the repository."
            ),
            details={"path": str(data_dir), "missing": missing_files},
        )
    return data_dir


def ensure_supported_format(command: str, *supported_formats: str) -> None:
    """Fail clearly when a command does not support the requested global format."""
    supported = tuple(dict.fromkeys(supported_formats))
    if state.format in supported:
        return
    handle_error(
        command,
        "ERR_VALIDATION_FORMAT",
        (
            f"Output format '{state.format}' is not supported for '{command}'."
            f" Supported formats: {', '.join(supported)}"
        ),
        details={"requested": state.format, "supported": list(supported)},
    )


def summarize_validation_error(error: Any) -> tuple[str, dict[str, Any]]:
    """Convert a Pydantic ValidationError into concise CLI-grade messages."""
    try:
        raw_issues = error.errors(include_url=False)
    except Exception:
        return ("Validation failed", {"issues": []})

    issues: list[dict[str, str]] = []
    for raw_issue in raw_issues:
        issue = cast(dict[str, Any], raw_issue)
        loc = ".".join(str(part) for part in cast(tuple[Any, ...], issue.get("loc", ()))) or "input"
        issue_type = str(issue.get("type", "validation_error"))
        ctx = cast(dict[str, Any], issue.get("ctx") or {})

        if issue_type == "missing":
            message = f"Missing required field: {loc}"
        elif issue_type in {"string_too_short", "too_short"}:
            message = f"Field '{loc}' must not be empty"
        elif issue_type == "literal_error":
            expected = ctx.get("expected")
            if expected:
                message = f"Field '{loc}' must be one of: {expected}"
            else:
                message = f"Field '{loc}' has an unsupported value"
        elif issue_type == "list_type":
            message = f"Field '{loc}' must be an array"
        elif issue_type == "dict_type":
            message = f"Field '{loc}' must be an object"
        elif issue_type == "string_type":
            message = f"Field '{loc}' must be a string"
        else:
            message = f"Invalid field '{loc}': {issue.get('msg', 'validation failed')}"

        issues.append({"field": loc, "type": issue_type, "message": message})

    if not issues:
        return ("Validation failed", {"issues": []})

    summary = issues[0]["message"]
    if len(issues) > 1:
        remaining = len(issues) - 1
        suffix = "issue" if remaining == 1 else "issues"
        summary = f"{summary} (+{remaining} more {suffix})"

    return (summary, {"issues": issues})


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

    if format not in {"json", "table", "markdown"}:
        handle_error(
            "archguard",
            "ERR_VALIDATION_FORMAT",
            f"Unknown global format: {format}",
            details={"requested": format, "supported": ["json", "table", "markdown"]},
        )

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
