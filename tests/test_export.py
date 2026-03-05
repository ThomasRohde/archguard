"""Tests for the export command."""

from __future__ import annotations

import csv
import io
import json

import orjson
from typer.testing import CliRunner

from guardrails_cli.cli import app

runner = CliRunner()

ADD_INPUT = json.dumps(
    {
        "title": "Prefer managed services",
        "severity": "should",
        "rationale": "Reduce ops burden",
        "guidance": "Use managed offerings",
        "scope": ["it-platform"],
        "applies_to": ["technology"],
        "owner": "Platform Team",
    }
)

ADD_INPUT_2 = json.dumps(
    {
        "title": "Encrypt data at rest",
        "severity": "must",
        "rationale": "Security compliance",
        "guidance": "All stores must use AES-256",
        "scope": ["it-platform"],
        "applies_to": ["data"],
        "owner": "Security Team",
    }
)


def _init_dir(tmp_path):
    data_dir = tmp_path / "guardrails"
    taxonomy = tmp_path / "taxonomy.json"
    taxonomy.write_bytes(
        orjson.dumps({"scope": ["it-platform", "data-platform", "channels"]})
    )
    result = runner.invoke(
        app, ["--data-dir", str(data_dir), "init", "--taxonomy", str(taxonomy)]
    )
    assert result.exit_code == 0
    return str(data_dir)


def _add_guardrail(dd, input_json=ADD_INPUT):
    result = runner.invoke(app, ["--data-dir", dd, "add"], input=input_json)
    assert result.exit_code == 0
    return orjson.loads(result.output)["guardrail"]["id"]


class TestExportJSON:
    def test_export_empty(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "json"])
        assert result.exit_code == 0
        data = orjson.loads(result.output)
        assert data == []

    def test_export_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "json"])
        assert result.exit_code == 0
        data = orjson.loads(result.output)
        assert len(data) == 2
        assert data[0]["title"] == "Prefer managed services"

    def test_export_filter_severity(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(
            app, ["--data-dir", dd, "export", "--format", "json", "--severity", "must"]
        )
        assert result.exit_code == 0
        data = orjson.loads(result.output)
        assert len(data) == 1
        assert data[0]["severity"] == "must"

    def test_export_filter_status(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "export", "--format", "json", "--status", "active"]
        )
        assert result.exit_code == 0
        data = orjson.loads(result.output)
        assert len(data) == 0

    def test_export_filter_scope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "export", "--format", "json", "--scope", "it-platform"]
        )
        assert result.exit_code == 0
        data = orjson.loads(result.output)
        assert len(data) == 1


class TestExportCSV:
    def test_export_csv_header(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "csv"])
        assert result.exit_code == 0
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["title"] == "Prefer managed services"
        assert rows[0]["scope"] == "it-platform"
        assert rows[0]["severity"] == "should"

    def test_export_csv_semicolons(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "csv"])
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        # applies_to should be semicolon-joined
        assert rows[0]["applies_to"] == "technology"

    def test_export_csv_multiple(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "csv"])
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 2


class TestExportMarkdown:
    def test_export_markdown_structure(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "markdown"])
        assert result.exit_code == 0
        assert "# Architecture Guardrails" in result.output
        assert "## Summary" in result.output
        assert "Prefer managed services" in result.output

    def test_export_markdown_grouped_by_scope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "export", "--format", "markdown"])
        assert "## it-platform" in result.output


class TestExportExplain:
    def test_explain(self) -> None:
        result = runner.invoke(app, ["export", "--explain"])
        assert result.exit_code == 0
        assert "export produces" in result.output
