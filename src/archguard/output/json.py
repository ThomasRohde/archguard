"""JSON output serialization using orjson."""

from __future__ import annotations

from typing import Any

import orjson


def success_response(data: dict[str, Any]) -> str:
    """Wrap data in a success envelope and serialize to JSON string."""
    envelope: dict[str, Any] = {"ok": True, **data}
    return orjson.dumps(envelope).decode()


def error_response(code: int, name: str, message: str, details: dict[str, Any]) -> str:
    """Create a structured error response JSON string."""
    envelope: dict[str, object] = {
        "ok": False,
        "error": {
            "code": code,
            "name": name,
            "message": message,
            "details": details,
        },
    }
    return orjson.dumps(envelope).decode()
