"""CLI integration tests using typer.testing.CliRunner."""

from __future__ import annotations

import json

import orjson
from typer.testing import CliRunner

from archguard.cli import app

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


def _init_dir(tmp_path):
    """Helper: init a data dir and return its path string."""
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


def _parse(output: str) -> dict:
    """Parse the JSON envelope from command output."""
    return orjson.loads(output)


def _assert_envelope(out: dict, *, ok: bool = True, command: str | None = None) -> None:
    """Assert standard envelope fields are present."""
    assert "schema_version" in out
    assert "request_id" in out
    assert "ok" in out
    assert "command" in out
    assert "result" in out
    assert "errors" in out
    assert "warnings" in out
    assert "metrics" in out
    assert isinstance(out["errors"], list)
    assert isinstance(out["warnings"], list)
    assert isinstance(out["metrics"], dict)
    assert "duration_ms" in out["metrics"]
    assert out["ok"] is ok
    if command is not None:
        assert out["command"] == command


class TestEnvelopeShape:
    """Verify that every command returns the canonical envelope (CLI-MANIFEST §1)."""

    def test_success_envelope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "list"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="list")
        assert out["result"] is not None

    def test_error_envelope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "get", "NONEXISTENT"])
        assert result.exit_code == 10
        out = _parse(result.output)
        _assert_envelope(out, ok=False, command="get")
        assert out["result"] is None
        assert len(out["errors"]) == 1
        assert out["errors"][0]["code"] == "ERR_RESOURCE_NOT_FOUND"


class TestInitCommand:
    def test_init_creates_data_dir(self, tmp_path) -> None:
        data_dir = tmp_path / "guardrails"
        result = runner.invoke(app, ["--data-dir", str(data_dir), "init"])
        assert result.exit_code == 0
        assert (data_dir / "guardrails.jsonl").exists()
        assert (data_dir / "references.jsonl").exists()
        assert (data_dir / "links.jsonl").exists()
        assert (data_dir / "taxonomy.json").exists()
        assert (data_dir / ".gitignore").exists()

    def test_init_with_taxonomy(self, tmp_path) -> None:
        taxonomy_file = tmp_path / "custom_taxonomy.json"
        taxonomy_file.write_bytes(orjson.dumps({"scope": ["custom-scope"]}))
        data_dir = tmp_path / "guardrails"
        result = runner.invoke(
            app, ["--data-dir", str(data_dir), "init", "--taxonomy", str(taxonomy_file)]
        )
        assert result.exit_code == 0
        loaded = orjson.loads((data_dir / "taxonomy.json").read_bytes())
        assert "custom-scope" in loaded["scope"]

    def test_init_explain(self) -> None:
        result = runner.invoke(app, ["init", "--explain"])
        assert result.exit_code == 0
        assert "init creates" in result.output


class TestBuildCommand:
    def test_build_empty_corpus(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "build"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="build")
        assert out["result"]["guardrails"] == 0

    def test_build_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        # Add a guardrail first
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "build"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["guardrails"] == 1


class TestValidateCommand:
    def test_validate_empty_corpus(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "validate"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="validate")

    def test_validate_with_valid_guardrail(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "validate"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True

    def test_validate_catches_orphan_ref(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        from pathlib import Path

        ref = {
            "guardrail_id": "NONEXISTENT",
            "ref_type": "adr",
            "ref_id": "ADR-001",
            "ref_title": "Test",
            "added_at": "2025-01-01T00:00:00Z",
        }
        (Path(dd) / "references.jsonl").write_bytes(orjson.dumps(ref) + b"\n")
        result = runner.invoke(app, ["--data-dir", dd, "validate"])
        assert result.exit_code == 10  # EXIT_VALIDATION
        out = _parse(result.output)
        assert out["ok"] is False
        assert len(out["errors"]) >= 1


class TestAddCommand:
    def test_add_success(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="add")
        assert out["result"]["guardrail"]["title"] == "Prefer managed services"
        assert len(out["result"]["guardrail"]["id"]) == 26  # ULID length

    def test_add_duplicate_title(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        assert result.exit_code == 40  # EXIT_CONFLICT
        out = _parse(result.output)
        assert out["ok"] is False
        assert out["errors"][0]["code"] == "ERR_CONFLICT_EXISTS"

    def test_add_invalid_scope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        bad_input = json.dumps(
            {
                "title": "Bad scope",
                "severity": "must",
                "rationale": "Test",
                "guidance": "Test",
                "scope": ["nonexistent-scope"],
                "applies_to": ["technology"],
                "owner": "Test",
            }
        )
        result = runner.invoke(app, ["--data-dir", dd, "add"], input=bad_input)
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_add_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "add"], input="not json")
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_add_with_references(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        input_with_refs = json.dumps(
            {
                "title": "With refs",
                "severity": "should",
                "rationale": "Test",
                "guidance": "Test",
                "scope": ["it-platform"],
                "applies_to": ["technology"],
                "owner": "Test",
                "references": [
                    {
                        "ref_type": "adr",
                        "ref_id": "ADR-001",
                        "ref_title": "Use managed services",
                    }
                ],
            }
        )
        result = runner.invoke(app, ["--data-dir", dd, "add"], input=input_with_refs)
        assert result.exit_code == 0
        out = _parse(result.output)
        assert len(out["result"]["references"]) == 1

    def test_add_explain(self) -> None:
        result = runner.invoke(app, ["add", "--explain"])
        assert result.exit_code == 0
        assert "add reads" in result.output

    def test_add_schema(self) -> None:
        result = runner.invoke(app, ["add", "--schema"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert "properties" in out["result"]["schema"]


class TestGetCommand:
    def test_get_existing(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        add_result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        guardrail_id = _parse(add_result.output)["result"]["guardrail"]["id"]

        result = runner.invoke(app, ["--data-dir", dd, "get", guardrail_id])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="get")
        assert out["result"]["guardrail"]["id"] == guardrail_id

    def test_get_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "get", "NONEXISTENT"])
        assert result.exit_code == 10  # EXIT_VALIDATION
        out = _parse(result.output)
        assert out["ok"] is False
        assert out["errors"][0]["code"] == "ERR_RESOURCE_NOT_FOUND"


class TestListCommand:
    def test_list_empty(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "list"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="list")
        assert out["result"]["total"] == 0

    def test_list_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["total"] == 1

    def test_list_filter_status(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        # Default status is "draft"
        result = runner.invoke(app, ["--data-dir", dd, "list", "--status", "draft"])
        out = _parse(result.output)
        assert out["result"]["total"] == 1

        result = runner.invoke(app, ["--data-dir", dd, "list", "--status", "active"])
        out = _parse(result.output)
        assert out["result"]["total"] == 0

    def test_list_filter_severity(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--severity", "should"])
        out = _parse(result.output)
        assert out["result"]["total"] == 1

    def test_list_filter_scope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--scope", "it-platform"])
        out = _parse(result.output)
        assert out["result"]["total"] == 1

        result = runner.invoke(app, ["--data-dir", dd, "list", "--scope", "data-platform"])
        out = _parse(result.output)
        assert out["result"]["total"] == 0

    def test_list_filter_owner(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--owner", "Platform Team"])
        out = _parse(result.output)
        assert out["result"]["total"] == 1

    def test_list_top(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        input2 = json.dumps(
            {
                "title": "Second guardrail",
                "severity": "must",
                "rationale": "Test",
                "guidance": "Test",
                "scope": ["it-platform"],
                "applies_to": ["technology"],
                "owner": "Test",
            }
        )
        runner.invoke(app, ["--data-dir", dd, "add"], input=input2)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--top", "1"])
        out = _parse(result.output)
        assert out["result"]["total"] == 2
        assert len(out["result"]["guardrails"]) == 1


class TestSearchCommand:
    def test_search_bm25_only(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(app, ["--data-dir", dd, "search", "managed services"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="search")
        assert out["result"]["total"] >= 1
        assert out["result"]["query"] == "managed services"

    def test_search_with_filter(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(
            app, ["--data-dir", dd, "search", "managed", "--severity", "should"]
        )
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True

    def test_search_no_bm25_results(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(app, ["--data-dir", dd, "search", "xyznotfoundquery"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True
        # BM25 should not match nonsense; vector may return low-score results
        for r in out["result"]["results"]:
            assert "bm25" not in r["match_sources"]

    def test_search_auto_builds_index(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        # No explicit build — search should auto-build
        result = runner.invoke(app, ["--data-dir", dd, "search", "managed"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True

    def test_search_explain(self) -> None:
        result = runner.invoke(app, ["search", "test", "--explain"])
        assert result.exit_code == 0
        assert "hybrid retrieval" in result.output

    def test_search_results_have_match_sources(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(app, ["--data-dir", dd, "search", "managed"])
        out = _parse(result.output)
        if out["result"]["total"] > 0:
            assert "bm25" in out["result"]["results"][0]["match_sources"]


class TestCheckCommand:
    def test_check_basic(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        context = json.dumps({
            "decision": "Use self-hosted Kafka for event streaming",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "tags": ["kafka", "self-hosted"],
        })
        result = runner.invoke(app, ["--data-dir", dd, "check"], input=context)
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="check")
        assert "summary" in out["result"]
        assert "must" in out["result"]["summary"]
        assert "should" in out["result"]["summary"]
        assert "may" in out["result"]["summary"]

    def test_check_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "check"], input="not json")
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_check_missing_decision(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        context = json.dumps({"scope": ["it-platform"]})
        result = runner.invoke(app, ["--data-dir", dd, "check"], input=context)
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_check_explain(self) -> None:
        result = runner.invoke(app, ["check", "--explain"])
        assert result.exit_code == 0
        assert "check reads" in result.output

    def test_check_context_preserved(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        context = json.dumps({
            "decision": "Use managed database",
            "tags": ["rds"],
        })
        result = runner.invoke(app, ["--data-dir", dd, "check"], input=context)
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["context"]["decision"] == "Use managed database"


class TestRelatedCommand:
    def test_related_no_links(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        add_result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        gid = _parse(add_result.output)["result"]["guardrail"]["id"]
        result = runner.invoke(app, ["--data-dir", dd, "related", gid])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="related")
        assert out["result"]["guardrail_id"] == gid
        assert out["result"]["related"] == []

    def test_related_with_links(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        add1 = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        gid1 = _parse(add1.output)["result"]["guardrail"]["id"]

        input2 = json.dumps({
            "title": "Encrypt data at rest",
            "severity": "must",
            "rationale": "Security compliance",
            "guidance": "All stores must use AES-256",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Security Team",
        })
        add2 = runner.invoke(app, ["--data-dir", dd, "add"], input=input2)
        gid2 = _parse(add2.output)["result"]["guardrail"]["id"]

        # Manually add a link
        from pathlib import Path

        link = {"from_id": gid1, "to_id": gid2, "rel_type": "supports", "note": "test"}
        (Path(dd) / "links.jsonl").write_bytes(orjson.dumps(link) + b"\n")

        result = runner.invoke(app, ["--data-dir", dd, "related", gid1])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True
        assert len(out["result"]["related"]) == 1
        assert out["result"]["related"][0]["id"] == gid2
        assert out["result"]["related"][0]["direction"] == "outgoing"
        assert out["result"]["related"][0]["rel_type"] == "supports"

        # Check from the other side
        result2 = runner.invoke(app, ["--data-dir", dd, "related", gid2])
        out2 = _parse(result2.output)
        assert len(out2["result"]["related"]) == 1
        assert out2["result"]["related"][0]["id"] == gid1
        assert out2["result"]["related"][0]["direction"] == "incoming"

    def test_related_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "related", "NONEXISTENT"])
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_related_explain(self) -> None:
        result = runner.invoke(app, ["related", "SOMEID", "--explain"])
        assert result.exit_code == 0
        assert "related returns" in result.output


class TestHelpFlags:
    def test_main_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "guardrails" in _strip_ansi(result.output).lower()

    def test_search_help(self) -> None:
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--status" in _strip_ansi(result.output)


# ---------------------------------------------------------------------------
# Milestone 3: Write & maintenance commands
# ---------------------------------------------------------------------------

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


def _add_guardrail(dd, input_json=ADD_INPUT):
    """Helper: add a guardrail and return its ID."""
    result = runner.invoke(app, ["--data-dir", dd, "add"], input=input_json)
    assert result.exit_code == 0
    return _parse(result.output)["result"]["guardrail"]["id"]


class TestUpdateCommand:
    def test_update_title(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"title": "Updated title"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="update")
        assert out["result"]["guardrail"]["title"] == "Updated title"

    def test_update_severity(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"severity": "must"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["guardrail"]["severity"] == "must"

    def test_update_scope_taxonomy_validation(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"scope": ["nonexistent-scope"]})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_update_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        patch = json.dumps({"title": "New"})
        result = runner.invoke(app, ["--data-dir", dd, "update", "NONEXISTENT"], input=patch)
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_update_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input="not json")
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_update_superseded_status_blocked(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"status": "superseded"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 40  # EXIT_CONFLICT

    def test_update_sets_updated_at(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        # Get original
        get_result = runner.invoke(app, ["--data-dir", dd, "get", gid])
        original_updated = _parse(get_result.output)["result"]["guardrail"]["updated_at"]
        patch = json.dumps({"guidance": "New guidance text"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        out = _parse(result.output)
        assert out["result"]["guardrail"]["updated_at"] != original_updated


class TestRefAddCommand:
    def test_ref_add_success(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        ref_input = json.dumps({
            "ref_type": "adr",
            "ref_id": "ADR-001",
            "ref_title": "Managed services decision",
        })
        result = runner.invoke(app, ["--data-dir", dd, "ref-add", gid], input=ref_input)
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="ref-add")
        assert out["result"]["reference"]["guardrail_id"] == gid
        assert out["result"]["reference"]["ref_id"] == "ADR-001"

    def test_ref_add_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        ref_input = json.dumps({
            "ref_type": "adr",
            "ref_id": "ADR-001",
            "ref_title": "Test",
        })
        result = runner.invoke(app, ["--data-dir", dd, "ref-add", "NONEXISTENT"], input=ref_input)
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_ref_add_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "ref-add", gid], input="bad json")
        assert result.exit_code == 10  # EXIT_VALIDATION


class TestLinkCommand:
    def test_link_success(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid1 = _add_guardrail(dd)
        gid2 = _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", gid1, gid2,
             "--rel", "supports", "--note", "Both reduce risk"],
        )
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="link")
        assert out["result"]["link"]["from_id"] == gid1
        assert out["result"]["link"]["to_id"] == gid2
        assert out["result"]["link"]["rel_type"] == "supports"

    def test_link_invalid_rel(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid1 = _add_guardrail(dd)
        gid2 = _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", gid1, gid2, "--rel", "invalid_rel"],
        )
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_link_from_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", "NONEXISTENT", gid, "--rel", "supports"],
        )
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_link_to_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", gid, "NONEXISTENT", "--rel", "supports"],
        )
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_link_visible_in_related(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid1 = _add_guardrail(dd)
        gid2 = _add_guardrail(dd, ADD_INPUT_2)
        runner.invoke(
            app,
            ["--data-dir", dd, "link", gid1, gid2, "--rel", "supports"],
        )
        result = runner.invoke(app, ["--data-dir", dd, "related", gid1])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert len(out["result"]["related"]) == 1
        assert out["result"]["related"][0]["id"] == gid2


class TestDeprecateCommand:
    def test_deprecate_active(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        # Update to active first
        patch = json.dumps({"status": "active"})
        runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", gid, "--reason", "Replaced"]
        )
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="deprecate")
        assert out["result"]["guardrail"]["status"] == "deprecated"
        assert out["result"]["guardrail"]["metadata"]["deprecation_reason"] == "Replaced"

    def test_deprecate_draft(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", gid, "--reason", "No longer needed"]
        )
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["guardrail"]["status"] == "deprecated"

    def test_deprecate_already_deprecated(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        runner.invoke(app, ["--data-dir", dd, "deprecate", gid, "--reason", "First"])
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", gid, "--reason", "Again"]
        )
        assert result.exit_code == 40  # EXIT_CONFLICT

    def test_deprecate_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", "NONEXISTENT", "--reason", "Gone"]
        )
        assert result.exit_code == 10  # EXIT_VALIDATION


class TestSupersedeCommand:
    def test_supersede_success(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        old_id = _add_guardrail(dd)
        new_id = _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", old_id, "--by", new_id]
        )
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="supersede")
        assert out["result"]["guardrail"]["status"] == "superseded"
        assert out["result"]["guardrail"]["superseded_by"] == new_id
        # Verify implements link was created
        assert out["result"]["link"]["from_id"] == new_id
        assert out["result"]["link"]["to_id"] == old_id
        assert out["result"]["link"]["rel_type"] == "implements"

    def test_supersede_creates_link_in_related(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        old_id = _add_guardrail(dd)
        new_id = _add_guardrail(dd, ADD_INPUT_2)
        runner.invoke(app, ["--data-dir", dd, "supersede", old_id, "--by", new_id])
        result = runner.invoke(app, ["--data-dir", dd, "related", old_id])
        out = _parse(result.output)
        assert len(out["result"]["related"]) == 1
        assert out["result"]["related"][0]["id"] == new_id

    def test_supersede_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", "NONEXISTENT", "--by", gid]
        )
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_supersede_replacement_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", gid, "--by", "NONEXISTENT"]
        )
        assert result.exit_code == 10  # EXIT_VALIDATION

    def test_supersede_invalid_transition(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        old_id = _add_guardrail(dd)
        new_id = _add_guardrail(dd, ADD_INPUT_2)
        # Deprecate old first
        runner.invoke(app, ["--data-dir", dd, "deprecate", old_id, "--reason", "Gone"])
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", old_id, "--by", new_id]
        )
        assert result.exit_code == 40  # EXIT_CONFLICT


class TestStatsCommand:
    def test_stats_empty(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="stats")
        assert out["result"]["total"] == 0
        assert out["result"]["stale"] == 0

    def test_stats_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["total"] == 2
        assert out["result"]["by_status"]["draft"] == 2
        assert out["result"]["by_severity"]["should"] == 1
        assert out["result"]["by_severity"]["must"] == 1
        assert out["result"]["by_scope"]["it-platform"] == 2

    def test_stats_stale_count(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        stale_input = json.dumps({
            "title": "Stale guardrail",
            "severity": "should",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2020-01-01",
        })
        _add_guardrail(dd, stale_input)
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        out = _parse(result.output)
        assert out["result"]["stale"] == 1

    def test_stats_mixed_statuses(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid1 = _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        # Deprecate one
        runner.invoke(app, ["--data-dir", dd, "deprecate", gid1, "--reason", "Old"])
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        out = _parse(result.output)
        assert out["result"]["by_status"]["deprecated"] == 1
        assert out["result"]["by_status"]["draft"] == 1


class TestReviewDueCommand:
    def test_review_due_none(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)  # No review_date
        result = runner.invoke(app, ["--data-dir", dd, "review-due"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="review-due")
        assert out["result"]["total"] == 0

    def test_review_due_with_overdue(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        overdue = json.dumps({
            "title": "Overdue guardrail",
            "severity": "must",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2020-06-15",
        })
        _add_guardrail(dd, overdue)
        result = runner.invoke(app, ["--data-dir", dd, "review-due"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["total"] == 1
        assert out["result"]["guardrails"][0]["review_date"] == "2020-06-15"

    def test_review_due_custom_before(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        g1 = json.dumps({
            "title": "Due soon",
            "severity": "should",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2025-06-01",
        })
        g2 = json.dumps({
            "title": "Due later",
            "severity": "must",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2026-12-01",
        })
        _add_guardrail(dd, g1)
        _add_guardrail(dd, g2)

        # Only one should be due before 2026-01-01
        result = runner.invoke(app, ["--data-dir", dd, "review-due", "--before", "2026-01-01"])
        out = _parse(result.output)
        assert out["result"]["total"] == 1
        assert out["result"]["cutoff"] == "2026-01-01"

        # Both due before 2027-01-01
        result2 = runner.invoke(app, ["--data-dir", dd, "review-due", "--before", "2027-01-01"])
        out2 = _parse(result2.output)
        assert out2["result"]["total"] == 2

    def test_review_due_sorted_ascending(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        later = json.dumps({
            "title": "Later review",
            "severity": "should",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2020-12-01",
        })
        earlier = json.dumps({
            "title": "Earlier review",
            "severity": "must",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2020-01-01",
        })
        _add_guardrail(dd, later)
        _add_guardrail(dd, earlier)
        result = runner.invoke(app, ["--data-dir", dd, "review-due"])
        out = _parse(result.output)
        assert out["result"]["total"] == 2
        assert out["result"]["guardrails"][0]["review_date"] == "2020-01-01"
        assert out["result"]["guardrails"][1]["review_date"] == "2020-12-01"


# ---------------------------------------------------------------------------
# Milestone 4: Import, Deduplicate, Format flag
# ---------------------------------------------------------------------------


class TestImportCommand:
    def test_import_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        import_file = tmp_path / "import.json"
        import_file.write_bytes(orjson.dumps([
            {
                "title": "Imported guardrail",
                "severity": "must",
                "rationale": "Imported",
                "guidance": "Imported guidance",
                "scope": ["it-platform"],
                "applies_to": ["technology"],
                "owner": "Import Team",
            }
        ]))
        result = runner.invoke(app, ["--data-dir", dd, "import", str(import_file)])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="import")
        assert out["result"]["imported"] == 1
        assert out["result"]["updated"] == 0

    def test_import_csv(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        import_file = tmp_path / "import.csv"
        import_file.write_text(
            "title,severity,rationale,guidance,scope,applies_to,owner\n"
            "CSV guardrail,should,Test reason,Test guidance,it-platform,technology,CSV Team\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["--data-dir", dd, "import", str(import_file)])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True
        assert out["result"]["imported"] == 1

    def test_import_upsert_by_title(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)  # "Prefer managed services"
        import_file = tmp_path / "import.json"
        import_file.write_bytes(orjson.dumps([
            {
                "title": "Prefer managed services",
                "severity": "must",
                "rationale": "Updated rationale",
                "guidance": "Updated guidance",
                "scope": ["it-platform"],
                "applies_to": ["technology"],
                "owner": "Updated Team",
            }
        ]))
        result = runner.invoke(app, ["--data-dir", dd, "import", str(import_file)])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["result"]["updated"] == 1
        assert out["result"]["imported"] == 0

    def test_import_invalid_file(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "import", "/nonexistent/file.json"])
        assert result.exit_code != 0

    def test_import_invalid_extension(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        import_file = tmp_path / "import.xml"
        import_file.write_text("<xml/>", encoding="utf-8")
        result = runner.invoke(app, ["--data-dir", dd, "import", str(import_file)])
        assert result.exit_code != 0

    def test_import_scope_validation(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        import_file = tmp_path / "import.json"
        import_file.write_bytes(orjson.dumps([
            {
                "title": "Bad scope guardrail",
                "severity": "must",
                "rationale": "Test",
                "guidance": "Test",
                "scope": ["nonexistent-scope"],
                "applies_to": ["technology"],
                "owner": "Test",
            }
        ]))
        result = runner.invoke(app, ["--data-dir", dd, "import", str(import_file)])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert len(out["result"]["errors"]) == 1
        assert out["result"]["imported"] == 0

    def test_import_explain(self, tmp_path) -> None:
        dummy = tmp_path / "dummy.json"
        dummy.write_text("[]", encoding="utf-8")
        result = runner.invoke(app, ["import", str(dummy), "--explain"])
        assert result.exit_code == 0
        assert "import reads" in result.output


class TestDeduplicateCommand:
    def test_deduplicate_empty(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "deduplicate"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="deduplicate")
        assert out["result"]["pairs"] == []
        assert out["result"]["total"] == 0

    def test_deduplicate_no_duplicates(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(app, ["--data-dir", dd, "deduplicate"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True
        # Different titles and guidance, should not be duplicates at default threshold

    def test_deduplicate_similar_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        g1 = json.dumps({
            "title": "Use managed database services",
            "severity": "should",
            "rationale": "Reduce operational burden",
            "guidance": "Use managed database services for production",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Platform Team",
        })
        g2 = json.dumps({
            "title": "Use managed database services always",
            "severity": "should",
            "rationale": "Reduce ops",
            "guidance": "Use managed database services for all environments",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Platform Team",
        })
        _add_guardrail(dd, g1)
        _add_guardrail(dd, g2)
        result = runner.invoke(app, ["--data-dir", dd, "deduplicate", "--threshold", "0.3"])
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True
        assert out["result"]["total"] >= 1
        assert out["result"]["pairs"][0]["method"] in ("jaccard", "embedding")

    def test_deduplicate_explain(self) -> None:
        result = runner.invoke(app, ["deduplicate", "--explain"])
        assert result.exit_code == 0
        assert "deduplicate computes" in result.output


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestFormatFlag:
    def test_list_table_format(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "-f", "table", "list"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "Prefer managed services" in plain
        # Should NOT be JSON envelope
        assert '"schema_version"' not in result.output

    def test_list_markdown_format(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "-f", "markdown", "list"])
        assert result.exit_code == 0
        assert "| ID |" in result.output
        assert "Prefer managed services" in result.output

    def test_stats_table_format(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "-f", "table", "stats"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "Guardrail Statistics" in plain
        assert '"schema_version"' not in result.output

    def test_stats_markdown_format(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "-f", "markdown", "stats"])
        assert result.exit_code == 0
        assert "**Total guardrails:**" in result.output

    def test_review_due_table_format(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        overdue = json.dumps({
            "title": "Overdue guardrail",
            "severity": "must",
            "rationale": "Test",
            "guidance": "Test",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "owner": "Test",
            "review_date": "2020-06-15",
        })
        _add_guardrail(dd, overdue)
        result = runner.invoke(app, ["--data-dir", dd, "-f", "table", "review-due"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "Reviews Due" in plain

    def test_json_default(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "list"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="list")


class TestGuideCommand:
    """Verify the guide command (CLI-MANIFEST §4)."""

    def test_guide_returns_envelope(self) -> None:
        result = runner.invoke(app, ["guide"])
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="guide")

    def test_guide_has_all_sections(self) -> None:
        result = runner.invoke(app, ["guide"])
        out = _parse(result.output)
        r = out["result"]
        assert "commands" in r
        assert "error_codes" in r
        assert "exit_codes" in r
        assert "envelope_schema" in r
        assert "examples" in r
        assert "global_options" in r
        assert "environment" in r
        assert "concurrency" in r
        assert "schema_version" in r
        assert "version" in r

    def test_guide_lists_all_commands(self) -> None:
        result = runner.invoke(app, ["guide"])
        cmds = _parse(result.output)["result"]["commands"]
        expected = {
            "init", "build", "validate", "search", "get", "list",
            "related", "check", "add", "update", "ref-add", "link",
            "delete", "deprecate", "supersede", "stats", "review-due",
            "deduplicate", "import", "export", "guide",
        }
        assert set(cmds.keys()) == expected

    def test_guide_commands_have_mutates_flag(self) -> None:
        result = runner.invoke(app, ["guide"])
        cmds = _parse(result.output)["result"]["commands"]
        for name, cmd in cmds.items():
            assert "mutates" in cmd, f"command '{name}' missing 'mutates' flag"

    def test_guide_error_codes_match_exit_map(self) -> None:
        result = runner.invoke(app, ["guide"])
        codes = _parse(result.output)["result"]["error_codes"]
        # Every error code should have exit_code, retryable, suggested_action
        for code, info in codes.items():
            assert "exit_code" in info, f"{code} missing exit_code"
            assert "retryable" in info, f"{code} missing retryable"
            assert "suggested_action" in info, f"{code} missing suggested_action"

    def test_guide_explain(self) -> None:
        result = runner.invoke(app, ["guide", "--explain"])
        assert result.exit_code == 0
        assert "machine-readable" in result.output


class TestLLMMode:
    """Verify LLM=true behavior (CLI-MANIFEST §8)."""

    def test_llm_true_forces_json(self, tmp_path) -> None:
        """LLM=true should force JSON output even if no format flag is given."""
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "list"], env={"LLM": "true"})
        assert result.exit_code == 0
        out = _parse(result.output)
        _assert_envelope(out, ok=True, command="list")

    def test_llm_true_explicit_format_overrides(self, tmp_path) -> None:
        """Explicit --format flag should still override LLM=true."""
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "-f", "table", "list"], env={"LLM": "true"}
        )
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "Prefer managed services" in plain

    def test_llm_false_no_effect(self, tmp_path) -> None:
        """LLM=false should have no effect."""
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "list"], env={"LLM": "false"})
        assert result.exit_code == 0
        out = _parse(result.output)
        assert out["ok"] is True
