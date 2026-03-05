"""Tests for SQLite index build and query operations."""

from __future__ import annotations

from pathlib import Path

from archguard.core.index import (
    build_index,
    create_schema,
    ensure_index,
    get_connection,
    is_stale,
)
from archguard.core.models import Guardrail, Link, Reference


class TestGetConnection:
    def test_connection_pragmas(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal == "wal"
        conn.close()


class TestCreateSchema:
    def test_tables_created(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        create_schema(conn)
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "guardrails" in tables
        assert "refs" in tables
        assert "links" in tables
        conn.close()


class TestBuildIndex:
    def test_inserts_guardrails(self, tmp_path: Path, sample_guardrail_dict: dict) -> None:
        db_path = tmp_path / "test.db"
        g = Guardrail.model_validate(sample_guardrail_dict)
        build_index(db_path, [g], [], [])

        conn = get_connection(db_path)
        row = conn.execute("SELECT id, title FROM guardrails").fetchone()
        assert row["id"] == g.id
        assert row["title"] == g.title
        conn.close()

    def test_inserts_refs(self, tmp_path: Path, sample_guardrail_dict: dict) -> None:
        db_path = tmp_path / "test.db"
        g = Guardrail.model_validate(sample_guardrail_dict)
        ref = Reference(
            guardrail_id=g.id,
            ref_type="adr",
            ref_id="ADR-001",
            ref_title="Use managed services",
            added_at="2025-01-01T00:00:00Z",
        )
        build_index(db_path, [g], [ref], [])

        conn = get_connection(db_path)
        row = conn.execute("SELECT ref_id FROM refs").fetchone()
        assert row["ref_id"] == "ADR-001"
        conn.close()

    def test_inserts_links(self, tmp_path: Path, sample_guardrail_dict: dict) -> None:
        db_path = tmp_path / "test.db"
        g1 = Guardrail.model_validate(sample_guardrail_dict)
        g2_dict = {**sample_guardrail_dict, "id": "01HXR00000000000000000TST2", "title": "Second"}
        g2 = Guardrail.model_validate(g2_dict)
        lnk = Link(from_id=g1.id, to_id=g2.id, rel_type="supports")
        build_index(db_path, [g1, g2], [], [lnk])

        conn = get_connection(db_path)
        row = conn.execute("SELECT rel_type FROM links").fetchone()
        assert row["rel_type"] == "supports"
        conn.close()

    def test_fts5_search(self, tmp_path: Path, sample_guardrail_dict: dict) -> None:
        db_path = tmp_path / "test.db"
        g = Guardrail.model_validate(sample_guardrail_dict)
        build_index(db_path, [g], [], [])

        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT title FROM guardrails_fts WHERE guardrails_fts MATCH ?", ("managed",)
        ).fetchall()
        assert len(rows) == 1
        assert "managed" in rows[0]["title"].lower()
        conn.close()

    def test_rebuild_clears_old_data(self, tmp_path: Path, sample_guardrail_dict: dict) -> None:
        db_path = tmp_path / "test.db"
        g = Guardrail.model_validate(sample_guardrail_dict)
        build_index(db_path, [g], [], [])
        # Rebuild with empty data
        build_index(db_path, [], [], [])

        conn = get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM guardrails").fetchone()[0]
        assert count == 0
        conn.close()


class TestEnsureIndex:
    def test_creates_db_when_missing(self, tmp_data_dir: Path) -> None:
        db_path = ensure_index(tmp_data_dir)
        assert db_path.exists()

    def test_skips_rebuild_when_fresh(self, tmp_data_dir: Path) -> None:
        db_path = ensure_index(tmp_data_dir)
        mtime1 = db_path.stat().st_mtime
        # Second call should not rebuild
        import time

        time.sleep(0.01)
        ensure_index(tmp_data_dir)
        mtime2 = db_path.stat().st_mtime
        assert mtime1 == mtime2


class TestIsStale:
    def test_missing_db(self, tmp_data_dir: Path) -> None:
        assert is_stale(tmp_data_dir / ".guardrails.db", tmp_data_dir) is True

    def test_fresh_db(self, tmp_data_dir: Path) -> None:
        import time

        db_path = tmp_data_dir / ".guardrails.db"
        # Touch JSONL files first, then create DB after
        time.sleep(0.01)
        db_path.touch()
        assert is_stale(db_path, tmp_data_dir) is False
