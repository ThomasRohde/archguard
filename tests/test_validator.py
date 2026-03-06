"""Tests for validate_corpus() with various error conditions."""

from __future__ import annotations

from pathlib import Path

import orjson

from archguard.core.validator import validate_corpus


class TestValidateCorpusClean:
    def test_empty_corpus(self, tmp_data_dir: Path) -> None:
        result = validate_corpus(tmp_data_dir)
        assert result.ok
        assert result.errors == []

    def test_valid_single_guardrail(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        (tmp_data_dir / "guardrails.jsonl").write_bytes(
            orjson.dumps(sample_guardrail_dict) + b"\n"
        )
        result = validate_corpus(tmp_data_dir)
        assert result.ok

    def test_active_guardrail_without_reference_warns(
        self, tmp_data_dir: Path, sample_guardrail_dict: dict
    ) -> None:
        (tmp_data_dir / "guardrails.jsonl").write_bytes(
            orjson.dumps(sample_guardrail_dict) + b"\n"
        )
        result = validate_corpus(tmp_data_dir)
        assert result.ok
        assert any("status is 'active' but no references found" in w for w in result.warnings)


class TestValidateCorpusErrors:
    def test_duplicate_ids(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        line = orjson.dumps(sample_guardrail_dict) + b"\n"
        (tmp_data_dir / "guardrails.jsonl").write_bytes(line + line)
        result = validate_corpus(tmp_data_dir)
        assert not result.ok
        assert any("Duplicate" in e for e in result.errors)

    def test_orphan_reference(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        (tmp_data_dir / "guardrails.jsonl").write_bytes(
            orjson.dumps(sample_guardrail_dict) + b"\n"
        )
        ref = {
            "guardrail_id": "NONEXISTENT",
            "ref_type": "adr",
            "ref_id": "ADR-001",
            "ref_title": "Some ADR",
            "added_at": "2025-01-01T00:00:00Z",
        }
        (tmp_data_dir / "references.jsonl").write_bytes(orjson.dumps(ref) + b"\n")
        result = validate_corpus(tmp_data_dir)
        assert not result.ok
        assert any("Orphan reference" in e for e in result.errors)

    def test_broken_link(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        (tmp_data_dir / "guardrails.jsonl").write_bytes(
            orjson.dumps(sample_guardrail_dict) + b"\n"
        )
        link = {
            "from_id": sample_guardrail_dict["id"],
            "to_id": "NONEXISTENT",
            "rel_type": "supports",
        }
        (tmp_data_dir / "links.jsonl").write_bytes(orjson.dumps(link) + b"\n")
        result = validate_corpus(tmp_data_dir)
        assert not result.ok
        assert any("Broken link" in e for e in result.errors)

    def test_invalid_scope(self, tmp_data_dir: Path, sample_guardrail_dict: dict) -> None:
        bad = {**sample_guardrail_dict, "scope": ["nonexistent-scope"]}
        (tmp_data_dir / "guardrails.jsonl").write_bytes(orjson.dumps(bad) + b"\n")
        result = validate_corpus(tmp_data_dir)
        assert not result.ok
        assert any("scope" in e for e in result.errors)

    def test_malformed_jsonl(self, tmp_data_dir: Path) -> None:
        (tmp_data_dir / "guardrails.jsonl").write_text("not valid json\n")
        result = validate_corpus(tmp_data_dir)
        assert not result.ok
        assert any("Failed to parse" in e for e in result.errors)
