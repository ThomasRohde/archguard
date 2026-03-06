"""Entry point for `python -m archguard` and the `guardrails` console script."""

import sys


def _ensure_utf8_stdout() -> None:
    """Force UTF-8 encoding on stdout/stderr to prevent mojibake on Windows.

    On Windows with CP850/CP1252 consoles, multibyte UTF-8 characters (§, —)
    are silently corrupted.  Reconfiguring to UTF-8 unconditionally is standard
    practice for CLI tools that emit non-ASCII content.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_ensure_utf8_stdout()

from archguard.cli import app  # noqa: E402


def main() -> None:
    app()


if __name__ == "__main__":
    main()
