"""SQLite index build and query operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson

from archguard.core.models import Guardrail, Link, Reference
from archguard.core.search_terms import derive_search_terms

SCHEMA_VERSION = 1


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with recommended pragmas."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables including FTS5 virtual table."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS guardrails (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            severity TEXT NOT NULL,
            rationale TEXT NOT NULL,
            guidance TEXT NOT NULL,
            exceptions TEXT DEFAULT '',
            consequences TEXT DEFAULT '',
            scope TEXT NOT NULL,          -- JSON array stored as text
            applies_to TEXT NOT NULL,     -- JSON array stored as text
            lifecycle_stage TEXT NOT NULL, -- JSON array stored as text
            owner TEXT NOT NULL,
            review_date TEXT,
            superseded_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            embedding BLOB              -- float32 vector
        );

        CREATE TABLE IF NOT EXISTS refs (
            guardrail_id TEXT NOT NULL REFERENCES guardrails(id),
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            ref_title TEXT NOT NULL,
            ref_url TEXT,
            excerpt TEXT DEFAULT '',
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS links (
            from_id TEXT NOT NULL REFERENCES guardrails(id),
            to_id TEXT NOT NULL REFERENCES guardrails(id),
            rel_type TEXT NOT NULL,
            note TEXT DEFAULT ''
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS guardrails_fts USING fts5(
            title, rationale, guidance, exceptions, scope,
            content='guardrails',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        );
    """)


def build_index(
    db_path: Path,
    guardrails: list[Guardrail],
    references: list[Reference],
    links: list[Link],
    embeddings: dict[str, bytes] | None = None,
) -> None:
    """Rebuild the full SQLite index from in-memory records.

    TODO: Implement the full build pipeline:
    1. Drop and recreate tables
    2. Insert guardrail rows with JSON-serialized array fields
    3. Insert reference and link rows
    4. Populate FTS5 index
    5. Store embedding BLOBs
    """
    conn = get_connection(db_path)
    try:
        # Drop existing data for full rebuild
        conn.executescript("""
            DROP TABLE IF EXISTS links;
            DROP TABLE IF EXISTS refs;
            DROP TABLE IF EXISTS guardrails_fts;
            DROP TABLE IF EXISTS guardrails;
            DROP TABLE IF EXISTS schema_version;
        """)
        create_schema(conn)

        # Insert schema version
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

        # Insert guardrails
        conn.executemany(
            """INSERT INTO guardrails
               (id, title, status, severity, rationale, guidance, exceptions, consequences,
                scope, applies_to, lifecycle_stage, owner, review_date, superseded_by,
                created_at, updated_at, metadata, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    g.id,
                    g.title,
                    g.status,
                    g.severity,
                    g.rationale,
                    g.guidance,
                    g.exceptions,
                    g.consequences,
                    orjson.dumps(g.scope).decode(),
                    orjson.dumps(g.applies_to).decode(),
                    orjson.dumps(g.lifecycle_stage).decode(),
                    g.owner,
                    g.review_date,
                    g.superseded_by,
                    g.created_at,
                    g.updated_at,
                    orjson.dumps(g.metadata).decode(),
                    embeddings.get(g.id) if embeddings else None,
                )
                for g in guardrails
            ],
        )

        # Insert refs
        conn.executemany(
            """INSERT INTO refs
               (guardrail_id, ref_type, ref_id, ref_title, ref_url, excerpt, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    r.guardrail_id, r.ref_type, r.ref_id, r.ref_title,
                    r.ref_url, r.excerpt, r.added_at,
                )
                for r in references
            ],
        )

        # Insert links
        conn.executemany(
            """INSERT INTO links (from_id, to_id, rel_type, note) VALUES (?, ?, ?, ?)""",
            [(lnk.from_id, lnk.to_id, lnk.rel_type, lnk.note) for lnk in links],
        )

        # Populate FTS5 with a small derived-term expansion to improve recall for
        # closely related infrastructure concepts such as Kafka <-> messaging brokers.
        row_ids = {
            row["id"]: row["rowid"]
            for row in conn.execute("SELECT rowid, id FROM guardrails").fetchall()
        }
        conn.executemany(
            """INSERT INTO guardrails_fts(rowid, title, rationale, guidance, exceptions, scope)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    row_ids[g.id],
                    g.title,
                    g.rationale,
                    g.guidance,
                    " ".join(part for part in [g.exceptions, *derive_search_terms(
                        " ".join([g.title, g.guidance, g.rationale, g.exceptions])
                    )] if part),
                    " ".join(g.scope),
                )
                for g in guardrails
            ],
        )

        conn.commit()
    finally:
        conn.close()


def ensure_index(data_dir: Path) -> Path:
    """Rebuild the SQLite index if stale. Returns the db_path."""
    from archguard.core.store import load_guardrails, load_links, load_references

    db_path = data_dir / ".guardrails.db"
    if is_stale(db_path, data_dir):
        guardrails = load_guardrails(data_dir)
        refs = load_references(data_dir)
        links = load_links(data_dir)

        embeddings: dict[str, bytes] | None = None
        try:
            from archguard.core.embeddings import (
                embed_guardrail,
                embedding_to_blob,
                try_load_model,
            )

            model = try_load_model(data_dir)
            if model is not None:
                embeddings = {
                    g.id: embedding_to_blob(embed_guardrail(model, g))
                    for g in guardrails
                }
        except Exception:
            embeddings = None

        build_index(db_path, guardrails, refs, links, embeddings=embeddings)
    return db_path


def is_stale(db_path: Path, jsonl_dir: Path) -> bool:
    """Check if the SQLite index is older than any JSONL file (lazy auto-build trigger)."""
    if not db_path.exists():
        return True
    db_mtime = db_path.stat().st_mtime
    return any(
        jsonl_file.stat().st_mtime > db_mtime
        for jsonl_file in jsonl_dir.glob("*.jsonl")
    )
