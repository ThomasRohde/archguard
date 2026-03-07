"""Unified JSON envelope serialization per CLI-MANIFEST.md."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import orjson
from ulid import ULID

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Request context — set once per invocation in the CLI callback
# ---------------------------------------------------------------------------

_start_time: float = 0.0
_request_id: str = ""


def init_request() -> None:
    """Initialise per-invocation request context (call once in the CLI callback)."""
    global _start_time, _request_id
    _start_time = time.monotonic()
    _request_id = f"req_{ULID()}"


def _elapsed_ms() -> int:
    if _start_time == 0.0:
        return 0
    return int((time.monotonic() - _start_time) * 1000)


# ---------------------------------------------------------------------------
# LLM / agent detection
# ---------------------------------------------------------------------------


def is_llm_mode() -> bool:
    """Return True when an AI agent is driving the CLI."""
    return os.environ.get("LLM", "").lower() == "true"


def is_interactive() -> bool:
    """Return True when stdout is a terminal (not piped/redirected)."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------


def envelope(
    command: str,
    result: dict[str, Any] | list[Any] | None = None,
    *,
    ok: bool = True,
    errors: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Build and serialize the canonical CLI response envelope.

    Every command — success or failure — returns this same top-level shape.
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "request_id": _request_id,
        "ok": ok,
        "command": command,
        "result": result,
        "errors": errors or [],
        "warnings": warnings or [],
        "metrics": {"duration_ms": _elapsed_ms()},
    }
    return orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode()


def error_envelope(
    command: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    suggested_action: str = "fix_input",
    retryable: bool = False,
) -> str:
    """Build a structured error envelope."""
    err: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "suggested_action": suggested_action,
    }
    if details:
        err["details"] = details
    return envelope(command, result=None, ok=False, errors=[err])


# ---------------------------------------------------------------------------
# Exit code mapping (PRD §12)
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 10
EXIT_ALREADY_EXISTS = 11
EXIT_INVALID_TRANSITION = 12
EXIT_VALIDATION = 20
EXIT_INTEGRITY = 21
EXIT_BUILD = 30
EXIT_MODEL = 31
EXIT_IO = 40
EXIT_INTERNAL = 50


ERROR_EXIT_MAP: dict[str, int] = {
    "ERR_RESOURCE_NOT_FOUND": EXIT_NOT_FOUND,
    "ERR_VALIDATION": EXIT_VALIDATION,
    "ERR_VALIDATION_JSON": EXIT_VALIDATION,
    "ERR_VALIDATION_INPUT": EXIT_VALIDATION,
    "ERR_VALIDATION_FORMAT": EXIT_VALIDATION,
    "ERR_VALIDATION_SCHEMA": EXIT_VALIDATION,
    "ERR_INTEGRITY": EXIT_INTEGRITY,
    "ERR_CONFLICT_EXISTS": EXIT_ALREADY_EXISTS,
    "ERR_CONFLICT_TRANSITION": EXIT_INVALID_TRANSITION,
    "ERR_BUILD": EXIT_BUILD,
    "ERR_MODEL": EXIT_MODEL,
    "ERR_IO_FILE_NOT_FOUND": EXIT_IO,
    "ERR_IO_FORMAT": EXIT_IO,
    "ERR_INTERNAL": EXIT_INTERNAL,
}


def exit_code_for(error_code: str) -> int:
    """Return the exit code for a given error code string."""
    return ERROR_EXIT_MAP.get(error_code, EXIT_INTERNAL)
