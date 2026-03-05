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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["guardrails"] == 0

    def test_build_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        # Add a guardrail first
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "build"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["guardrails"] == 1


class TestValidateCommand:
    def test_validate_empty_corpus(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "validate"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True

    def test_validate_with_valid_guardrail(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "validate"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
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
        assert result.exit_code == 21
        out = orjson.loads(result.output)
        assert out["ok"] is False


class TestAddCommand:
    def test_add_success(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["guardrail"]["title"] == "Prefer managed services"
        assert len(out["guardrail"]["id"]) == 26  # ULID length

    def test_add_duplicate_title(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        assert result.exit_code == 11
        out = orjson.loads(result.output)
        assert out["ok"] is False
        assert "already_exists" in out["error"]["name"]

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
        assert result.exit_code == 20

    def test_add_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "add"], input="not json")
        assert result.exit_code == 20

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
        out = orjson.loads(result.output)
        assert len(out["references"]) == 1

    def test_add_explain(self) -> None:
        result = runner.invoke(app, ["add", "--explain"])
        assert result.exit_code == 0
        assert "add reads" in result.output

    def test_add_schema(self) -> None:
        result = runner.invoke(app, ["add", "--schema"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert "properties" in out


class TestGetCommand:
    def test_get_existing(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        add_result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        guardrail_id = orjson.loads(add_result.output)["guardrail"]["id"]

        result = runner.invoke(app, ["--data-dir", dd, "get", guardrail_id])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["guardrail"]["id"] == guardrail_id

    def test_get_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "get", "NONEXISTENT"])
        assert result.exit_code == 10
        out = orjson.loads(result.output)
        assert out["ok"] is False
        assert "not_found" in out["error"]["name"]


class TestListCommand:
    def test_list_empty(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "list"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["total"] == 0

    def test_list_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["total"] == 1

    def test_list_filter_status(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        # Default status is "draft"
        result = runner.invoke(app, ["--data-dir", dd, "list", "--status", "draft"])
        out = orjson.loads(result.output)
        assert out["total"] == 1

        result = runner.invoke(app, ["--data-dir", dd, "list", "--status", "active"])
        out = orjson.loads(result.output)
        assert out["total"] == 0

    def test_list_filter_severity(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--severity", "should"])
        out = orjson.loads(result.output)
        assert out["total"] == 1

    def test_list_filter_scope(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--scope", "it-platform"])
        out = orjson.loads(result.output)
        assert out["total"] == 1

        result = runner.invoke(app, ["--data-dir", dd, "list", "--scope", "data-platform"])
        out = orjson.loads(result.output)
        assert out["total"] == 0

    def test_list_filter_owner(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        result = runner.invoke(app, ["--data-dir", dd, "list", "--owner", "Platform Team"])
        out = orjson.loads(result.output)
        assert out["total"] == 1

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
        out = orjson.loads(result.output)
        assert out["total"] == 2
        assert len(out["guardrails"]) == 1


class TestSearchCommand:
    def test_search_bm25_only(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(app, ["--data-dir", dd, "search", "managed services"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["total"] >= 1
        assert out["query"] == "managed services"

    def test_search_with_filter(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(
            app, ["--data-dir", dd, "search", "managed", "--severity", "should"]
        )
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True

    def test_search_no_results(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        runner.invoke(app, ["--data-dir", dd, "build"])
        result = runner.invoke(app, ["--data-dir", dd, "search", "xyznotfoundquery"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["total"] == 0

    def test_search_auto_builds_index(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        # No explicit build — search should auto-build
        result = runner.invoke(app, ["--data-dir", dd, "search", "managed"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
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
        out = orjson.loads(result.output)
        if out["total"] > 0:
            assert "bm25" in out["results"][0]["match_sources"]


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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert "summary" in out
        assert "must" in out["summary"]
        assert "should" in out["summary"]
        assert "may" in out["summary"]

    def test_check_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "check"], input="not json")
        assert result.exit_code == 20

    def test_check_missing_decision(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        context = json.dumps({"scope": ["it-platform"]})
        result = runner.invoke(app, ["--data-dir", dd, "check"], input=context)
        assert result.exit_code == 20

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
        out = orjson.loads(result.output)
        assert out["context"]["decision"] == "Use managed database"


class TestRelatedCommand:
    def test_related_no_links(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        add_result = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        gid = orjson.loads(add_result.output)["guardrail"]["id"]
        result = runner.invoke(app, ["--data-dir", dd, "related", gid])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["guardrail_id"] == gid
        assert out["related"] == []

    def test_related_with_links(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        add1 = runner.invoke(app, ["--data-dir", dd, "add"], input=ADD_INPUT)
        gid1 = orjson.loads(add1.output)["guardrail"]["id"]

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
        gid2 = orjson.loads(add2.output)["guardrail"]["id"]

        # Manually add a link
        from pathlib import Path

        link = {"from_id": gid1, "to_id": gid2, "rel_type": "supports", "note": "test"}
        (Path(dd) / "links.jsonl").write_bytes(orjson.dumps(link) + b"\n")

        result = runner.invoke(app, ["--data-dir", dd, "related", gid1])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert len(out["related"]) == 1
        assert out["related"][0]["id"] == gid2
        assert out["related"][0]["direction"] == "outgoing"
        assert out["related"][0]["rel_type"] == "supports"

        # Check from the other side
        result2 = runner.invoke(app, ["--data-dir", dd, "related", gid2])
        out2 = orjson.loads(result2.output)
        assert len(out2["related"]) == 1
        assert out2["related"][0]["id"] == gid1
        assert out2["related"][0]["direction"] == "incoming"

    def test_related_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "related", "NONEXISTENT"])
        assert result.exit_code == 10

    def test_related_explain(self) -> None:
        result = runner.invoke(app, ["related", "SOMEID", "--explain"])
        assert result.exit_code == 0
        assert "related returns" in result.output


class TestHelpFlags:
    def test_main_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "guardrails" in result.output.lower()

    def test_search_help(self) -> None:
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.output


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
    return orjson.loads(result.output)["guardrail"]["id"]


class TestUpdateCommand:
    def test_update_title(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"title": "Updated title"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["guardrail"]["title"] == "Updated title"

    def test_update_severity(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"severity": "must"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["guardrail"]["severity"] == "must"

    def test_update_scope_taxonomy_validation(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"scope": ["nonexistent-scope"]})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 20

    def test_update_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        patch = json.dumps({"title": "New"})
        result = runner.invoke(app, ["--data-dir", dd, "update", "NONEXISTENT"], input=patch)
        assert result.exit_code == 10

    def test_update_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input="not json")
        assert result.exit_code == 20

    def test_update_superseded_status_blocked(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        patch = json.dumps({"status": "superseded"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        assert result.exit_code == 12

    def test_update_sets_updated_at(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        # Get original
        get_result = runner.invoke(app, ["--data-dir", dd, "get", gid])
        original_updated = orjson.loads(get_result.output)["guardrail"]["updated_at"]
        patch = json.dumps({"guidance": "New guidance text"})
        result = runner.invoke(app, ["--data-dir", dd, "update", gid], input=patch)
        out = orjson.loads(result.output)
        assert out["guardrail"]["updated_at"] != original_updated


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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["reference"]["guardrail_id"] == gid
        assert out["reference"]["ref_id"] == "ADR-001"

    def test_ref_add_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        ref_input = json.dumps({
            "ref_type": "adr",
            "ref_id": "ADR-001",
            "ref_title": "Test",
        })
        result = runner.invoke(app, ["--data-dir", dd, "ref-add", "NONEXISTENT"], input=ref_input)
        assert result.exit_code == 10

    def test_ref_add_invalid_json(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(app, ["--data-dir", dd, "ref-add", gid], input="bad json")
        assert result.exit_code == 20


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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["link"]["from_id"] == gid1
        assert out["link"]["to_id"] == gid2
        assert out["link"]["rel_type"] == "supports"

    def test_link_invalid_rel(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid1 = _add_guardrail(dd)
        gid2 = _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", gid1, gid2, "--rel", "invalid_rel"],
        )
        assert result.exit_code == 20

    def test_link_from_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", "NONEXISTENT", gid, "--rel", "supports"],
        )
        assert result.exit_code == 10

    def test_link_to_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app,
            ["--data-dir", dd, "link", gid, "NONEXISTENT", "--rel", "supports"],
        )
        assert result.exit_code == 10

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
        out = orjson.loads(result.output)
        assert len(out["related"]) == 1
        assert out["related"][0]["id"] == gid2


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
        out = orjson.loads(result.output)
        assert out["guardrail"]["status"] == "deprecated"
        assert out["guardrail"]["metadata"]["deprecation_reason"] == "Replaced"

    def test_deprecate_draft(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", gid, "--reason", "No longer needed"]
        )
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["guardrail"]["status"] == "deprecated"

    def test_deprecate_already_deprecated(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        runner.invoke(app, ["--data-dir", dd, "deprecate", gid, "--reason", "First"])
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", gid, "--reason", "Again"]
        )
        assert result.exit_code == 12

    def test_deprecate_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(
            app, ["--data-dir", dd, "deprecate", "NONEXISTENT", "--reason", "Gone"]
        )
        assert result.exit_code == 10


class TestSupersedeCommand:
    def test_supersede_success(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        old_id = _add_guardrail(dd)
        new_id = _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", old_id, "--by", new_id]
        )
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["guardrail"]["status"] == "superseded"
        assert out["guardrail"]["superseded_by"] == new_id
        # Verify implements link was created
        assert out["link"]["from_id"] == new_id
        assert out["link"]["to_id"] == old_id
        assert out["link"]["rel_type"] == "implements"

    def test_supersede_creates_link_in_related(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        old_id = _add_guardrail(dd)
        new_id = _add_guardrail(dd, ADD_INPUT_2)
        runner.invoke(app, ["--data-dir", dd, "supersede", old_id, "--by", new_id])
        result = runner.invoke(app, ["--data-dir", dd, "related", old_id])
        out = orjson.loads(result.output)
        assert len(out["related"]) == 1
        assert out["related"][0]["id"] == new_id

    def test_supersede_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", "NONEXISTENT", "--by", gid]
        )
        assert result.exit_code == 10

    def test_supersede_replacement_not_found(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid = _add_guardrail(dd)
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", gid, "--by", "NONEXISTENT"]
        )
        assert result.exit_code == 10

    def test_supersede_invalid_transition(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        old_id = _add_guardrail(dd)
        new_id = _add_guardrail(dd, ADD_INPUT_2)
        # Deprecate old first
        runner.invoke(app, ["--data-dir", dd, "deprecate", old_id, "--reason", "Gone"])
        result = runner.invoke(
            app, ["--data-dir", dd, "supersede", old_id, "--by", new_id]
        )
        assert result.exit_code == 12


class TestStatsCommand:
    def test_stats_empty(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["total"] == 0
        assert out["stale"] == 0

    def test_stats_with_guardrails(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["total"] == 2
        assert out["by_status"]["draft"] == 2
        assert out["by_severity"]["should"] == 1
        assert out["by_severity"]["must"] == 1
        assert out["by_scope"]["it-platform"] == 2

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
        out = orjson.loads(result.output)
        assert out["stale"] == 1

    def test_stats_mixed_statuses(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        gid1 = _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        # Deprecate one
        runner.invoke(app, ["--data-dir", dd, "deprecate", gid1, "--reason", "Old"])
        result = runner.invoke(app, ["--data-dir", dd, "stats"])
        out = orjson.loads(result.output)
        assert out["by_status"]["deprecated"] == 1
        assert out["by_status"]["draft"] == 1


class TestReviewDueCommand:
    def test_review_due_none(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)  # No review_date
        result = runner.invoke(app, ["--data-dir", dd, "review-due"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["total"] == 0

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
        out = orjson.loads(result.output)
        assert out["total"] == 1
        assert out["guardrails"][0]["review_date"] == "2020-06-15"

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
        out = orjson.loads(result.output)
        assert out["total"] == 1
        assert out["cutoff"] == "2026-01-01"

        # Both due before 2027-01-01
        result2 = runner.invoke(app, ["--data-dir", dd, "review-due", "--before", "2027-01-01"])
        out2 = orjson.loads(result2.output)
        assert out2["total"] == 2

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
        out = orjson.loads(result.output)
        assert out["total"] == 2
        assert out["guardrails"][0]["review_date"] == "2020-01-01"
        assert out["guardrails"][1]["review_date"] == "2020-12-01"


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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["imported"] == 1
        assert out["updated"] == 0

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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["imported"] == 1

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
        out = orjson.loads(result.output)
        assert out["updated"] == 1
        assert out["imported"] == 0

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
        out = orjson.loads(result.output)
        assert len(out["errors"]) == 1
        assert out["imported"] == 0

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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["pairs"] == []
        assert out["total"] == 0

    def test_deduplicate_no_duplicates(self, tmp_path) -> None:
        dd = _init_dir(tmp_path)
        _add_guardrail(dd)
        _add_guardrail(dd, ADD_INPUT_2)
        result = runner.invoke(app, ["--data-dir", dd, "deduplicate"])
        assert result.exit_code == 0
        out = orjson.loads(result.output)
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
        out = orjson.loads(result.output)
        assert out["ok"] is True
        assert out["total"] >= 1
        assert out["pairs"][0]["method"] == "jaccard"

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
        # Should NOT be JSON
        assert '{"ok"' not in result.output

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
        assert '{"ok"' not in result.output

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
        out = orjson.loads(result.output)
        assert out["ok"] is True
