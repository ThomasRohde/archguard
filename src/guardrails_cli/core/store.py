"""JSONL read/write operations — the source-of-truth persistence layer."""

from __future__ import annotations

from pathlib import Path

import orjson
from pydantic import BaseModel

from guardrails_cli.core.models import Guardrail, Link, Reference


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    """Read and validate all records from a JSONL file."""
    if not path.exists():
        return []
    records: list[T] = []
    for _line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        data = orjson.loads(stripped)
        records.append(model.model_validate(data))
    return records


def append_jsonl(path: Path, record: BaseModel) -> None:
    """Append a single record to a JSONL file."""
    line = orjson.dumps(record.model_dump(), option=orjson.OPT_APPEND_NEWLINE)
    with open(path, "ab") as f:
        f.write(line)


def rewrite_jsonl(path: Path, records: list[BaseModel]) -> None:
    """Rewrite an entire JSONL file from a list of records (edit semantics)."""
    with open(path, "wb") as f:
        for record in records:
            f.write(orjson.dumps(record.model_dump(), option=orjson.OPT_APPEND_NEWLINE))


def load_taxonomy(data_dir: Path) -> list[str]:
    """Load scope vocabulary from taxonomy.json. Returns empty list if unconstrained."""
    taxonomy_path = data_dir / "taxonomy.json"
    if not taxonomy_path.exists():
        return []
    data = orjson.loads(taxonomy_path.read_bytes())
    return data.get("scope", [])


def load_guardrails(data_dir: Path) -> list[Guardrail]:
    """Load all guardrails from the data directory."""
    return read_jsonl(data_dir / "guardrails.jsonl", Guardrail)


def load_references(data_dir: Path) -> list[Reference]:
    """Load all references from the data directory."""
    return read_jsonl(data_dir / "references.jsonl", Reference)


def load_links(data_dir: Path) -> list[Link]:
    """Load all links from the data directory."""
    return read_jsonl(data_dir / "links.jsonl", Link)
