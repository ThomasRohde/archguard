"""Tests for JSONL read/write operations."""

from __future__ import annotations

from pathlib import Path

import orjson

from archguard.core.models import Guardrail
from archguard.core.store import (
    append_jsonl,
    load_taxonomy,
    read_jsonl,
    rewrite_jsonl,
)


class TestReadJsonl:
    def test_empty_file(self, tmp_data_dir: Path) -> None:
        result = read_jsonl(tmp_data_dir / "guardrails.jsonl", Guardrail)
        assert result == []

    def test_read_single_record(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        path = tmp_data_dir / "guardrails.jsonl"
        path.write_bytes(orjson.dumps(sample_guardrail_dict) + b"\n")
        result = read_jsonl(path, Guardrail)
        assert len(result) == 1
        assert result[0].title == sample_guardrail_dict["title"]

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = read_jsonl(tmp_path / "missing.jsonl", Guardrail)
        assert result == []


class TestAppendJsonl:
    def test_append_creates_line(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        path = tmp_data_dir / "guardrails.jsonl"
        guardrail = Guardrail.model_validate(sample_guardrail_dict)
        append_jsonl(path, guardrail)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = orjson.loads(lines[0])
        assert data["id"] == sample_guardrail_dict["id"]


class TestRewriteJsonl:
    def test_rewrite_replaces_content(
        self, tmp_data_dir: Path, sample_guardrail_dict: dict
    ) -> None:
        path = tmp_data_dir / "guardrails.jsonl"
        g = Guardrail.model_validate(sample_guardrail_dict)
        append_jsonl(path, g)
        append_jsonl(path, g)
        assert len(read_jsonl(path, Guardrail)) == 2

        rewrite_jsonl(path, [g])
        assert len(read_jsonl(path, Guardrail)) == 1


class TestLoadTaxonomy:
    def test_load_existing(self, tmp_data_dir: Path) -> None:
        taxonomy = load_taxonomy(tmp_data_dir)
        assert "it-platform" in taxonomy

    def test_missing_file(self, tmp_path: Path) -> None:
        taxonomy = load_taxonomy(tmp_path)
        assert taxonomy == []
