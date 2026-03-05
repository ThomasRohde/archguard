"""Unit tests for output/table.py and output/markdown.py formatters."""

from __future__ import annotations

from archguard.core.models import Guardrail, Link, Reference, SearchResult


def _make_guardrail(**overrides) -> Guardrail:
    defaults = {
        "id": "01HTEST01ABCDEFGHIJKLMNOP",
        "title": "Test guardrail",
        "status": "active",
        "severity": "must",
        "rationale": "Test rationale",
        "guidance": "Test guidance",
        "scope": ["it-platform"],
        "applies_to": ["technology"],
        "owner": "Test Team",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return Guardrail(**defaults)


def _make_search_result(**overrides) -> SearchResult:
    defaults = {
        "id": "01HTEST01ABCDEFGHIJKLMNOP",
        "title": "Test result",
        "severity": "should",
        "status": "active",
        "score": 0.85,
        "match_sources": ["bm25"],
        "snippet": "some snippet",
    }
    defaults.update(overrides)
    return SearchResult(**defaults)


def _make_ref(**overrides) -> Reference:
    defaults = {
        "guardrail_id": "01HTEST01ABCDEFGHIJKLMNOP",
        "ref_type": "adr",
        "ref_id": "ADR-001",
        "ref_title": "Test ADR",
        "added_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return Reference(**defaults)


def _make_link(**overrides) -> Link:
    defaults = {
        "from_id": "01HTEST01ABCDEFGHIJKLMNOP",
        "to_id": "01HTEST02ABCDEFGHIJKLMNOP",
        "rel_type": "supports",
    }
    defaults.update(overrides)
    return Link(**defaults)


class TestTableFormatter:
    def test_format_guardrail_list(self) -> None:
        from archguard.output.table import format_guardrail_list

        g = _make_guardrail()
        output = format_guardrail_list([g], 1)
        assert "01HTEST0" in output
        assert "Test guardrail" in output
        assert "1" in output  # total
        assert "must" in output

    def test_format_guardrail_list_empty(self) -> None:
        from archguard.output.table import format_guardrail_list

        output = format_guardrail_list([], 0)
        assert "0" in output

    def test_format_search_results(self) -> None:
        from archguard.output.table import format_search_results

        r = _make_search_result()
        output = format_search_results([r], 1, "test query")
        assert "test query" in output
        assert "Test result" in output
        assert "0.85" in output
        assert "bm25" in output

    def test_format_stats(self) -> None:
        from archguard.output.table import format_stats

        stats_dict = {
            "total": 5,
            "by_status": {"active": 3, "draft": 2},
            "by_severity": {"must": 2, "should": 3},
            "by_scope": {"it-platform": 5},
            "stale": 1,
        }
        output = format_stats(stats_dict)
        assert "5" in output
        assert "active" in output
        assert "must" in output
        assert "it-platform" in output
        assert "Stale" in output

    def test_format_review_due(self) -> None:
        from archguard.output.table import format_review_due

        g = _make_guardrail(review_date="2020-01-01")
        output = format_review_due([g], "2025-06-01")
        assert "01HTEST0" in output
        assert "2020-01-01" in output

    def test_format_guardrail_detail(self) -> None:
        from archguard.output.table import format_guardrail_detail

        g = _make_guardrail(exceptions="No exceptions")
        ref = _make_ref()
        link = _make_link()
        output = format_guardrail_detail(g, [ref], [link])
        assert "Test guardrail" in output
        assert "Test guidance" in output
        assert "Test rationale" in output
        assert "No exceptions" in output
        assert "ADR" in output or "adr" in output
        assert "supports" in output

    def test_format_guardrail_detail_no_refs_links(self) -> None:
        from archguard.output.table import format_guardrail_detail

        g = _make_guardrail()
        output = format_guardrail_detail(g, [], [])
        assert "Test guardrail" in output


class TestMarkdownFormatter:
    def test_format_guardrail_list_md(self) -> None:
        from archguard.output.markdown import format_guardrail_list_md

        g = _make_guardrail()
        output = format_guardrail_list_md([g], 1)
        assert "| ID |" in output
        assert "01HTEST0" in output
        assert "Test guardrail" in output
        assert "*1 total*" in output

    def test_format_guardrail_list_md_empty(self) -> None:
        from archguard.output.markdown import format_guardrail_list_md

        output = format_guardrail_list_md([], 0)
        assert "*0 total*" in output

    def test_format_export_md(self) -> None:
        from archguard.output.markdown import format_export_md

        g = _make_guardrail()
        ref = _make_ref()
        output = format_export_md([g], [ref])
        assert "# Architecture Guardrails" in output
        assert "## Summary" in output
        assert "## it-platform" in output
        assert "Test guardrail" in output
        assert "Test ADR" in output

    def test_format_export_md_severity_order(self) -> None:
        from archguard.output.markdown import format_export_md

        g1 = _make_guardrail(title="May rule", severity="may")
        g2 = _make_guardrail(title="Must rule", severity="must", id="01HTEST02ABCDEFGHIJKLMNOP")
        output = format_export_md([g1, g2], [])
        # must should appear before may within the same scope group
        must_pos = output.index("Must rule")
        may_pos = output.index("May rule")
        assert must_pos < may_pos

    def test_format_stats_md(self) -> None:
        from archguard.output.markdown import format_stats_md

        stats_dict = {
            "total": 3,
            "by_status": {"active": 2, "draft": 1},
            "by_severity": {"must": 1, "should": 2},
            "by_scope": {"it-platform": 3},
            "stale": 0,
        }
        output = format_stats_md(stats_dict)
        assert "**Total guardrails:** 3" in output
        assert "### By Status" in output
        assert "active" in output

    def test_format_review_due_md(self) -> None:
        from archguard.output.markdown import format_review_due_md

        g = _make_guardrail(review_date="2020-01-01")
        output = format_review_due_md([g], "2025-06-01")
        assert "## Reviews Due" in output
        assert "2020-01-01" in output
        assert "01HTEST0" in output
