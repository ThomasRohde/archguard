"""JSON output serialization using orjson."""

from __future__ import annotations

import orjson


def success_response(data: dict) -> str:  # type: ignore[type-arg]
    """Wrap data in a success envelope and serialize to JSON string."""
    envelope = {"ok": True, **data}
    return orjson.dumps(envelope).decode()


def error_response(code: int, name: str, message: str, details: dict) -> str:  # type: ignore[type-arg]
    """Create a structured error response JSON string."""
    envelope = {
        "ok": False,
        "error": {
            "code": code,
            "name": name,
            "message": message,
            "details": details,
        },
    }
    return orjson.dumps(envelope).decode()
