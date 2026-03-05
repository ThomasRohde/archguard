"""Hybrid search: BM25 (FTS5) + vector similarity + Reciprocal Rank Fusion."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import orjson

from archguard.core.embeddings import blob_to_embedding, cosine_similarity
from archguard.core.models import SearchResult

RRF_K = 60


def rrf_score(ranks: list[int], k: int = RRF_K) -> float:
    """Compute RRF score from a list of ranks (1-indexed)."""
    return sum(1.0 / (k + rank) for rank in ranks)


@dataclass
class RankedDoc:
    """Intermediate representation for RRF merging."""

    doc_id: str
    bm25_rank: int | None = None
    vector_rank: int | None = None

    @property
    def rrf(self) -> float:
        ranks = []
        if self.bm25_rank is not None:
            ranks.append(self.bm25_rank)
        if self.vector_rank is not None:
            ranks.append(self.vector_rank)
        return rrf_score(ranks) if ranks else 0.0


def bm25_search(conn: sqlite3.Connection, query: str, limit: int = 100) -> list[tuple[str, int]]:
    """Execute FTS5 MATCH query and return [(doc_id, rank_position)] (1-indexed)."""
    try:
        rows = conn.execute(
            "SELECT id, rank FROM guardrails g JOIN guardrails_fts f ON g.rowid = f.rowid "
            "WHERE guardrails_fts MATCH ? ORDER BY f.rank LIMIT ?",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(row[0], i + 1) for i, row in enumerate(rows)]


def vector_search(
    conn: sqlite3.Connection,
    query_embedding,  # type: ignore[type-arg]
    limit: int = 100,
) -> list[tuple[str, int]]:
    """Load all non-NULL embeddings, compute cosine similarity, return top results."""
    import numpy as np

    rows = conn.execute(
        "SELECT id, embedding FROM guardrails WHERE embedding IS NOT NULL"
    ).fetchall()
    if not rows:
        return []

    scored: list[tuple[str, float]] = []
    for row in rows:
        emb = blob_to_embedding(row[1])
        sim = cosine_similarity(np.array(query_embedding, dtype=np.float32), emb)
        scored.append((row[0], sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [(doc_id, i + 1) for i, (doc_id, _) in enumerate(scored[:limit])]


def hybrid_search(
    db_path: Path,
    query: str,
    model=None,
    filters: dict | None = None,  # type: ignore[type-arg]
    top: int = 10,
) -> tuple[list[SearchResult], int]:
    """Run hybrid BM25+vector search with RRF fusion and filters."""
    from archguard.core.index import get_connection

    conn = get_connection(db_path)
    try:
        # BM25 search
        bm25_results = bm25_search(conn, query)
        match_sources_map: dict[str, list[str]] = {}
        for doc_id, _ in bm25_results:
            match_sources_map.setdefault(doc_id, []).append("bm25")

        # Vector search (if model available)
        vector_results: list[tuple[str, int]] = []
        if model is not None:
            from archguard.core.embeddings import embed_text

            query_embedding = embed_text(model, query)
            vector_results = vector_search(conn, query_embedding)
            for doc_id, _ in vector_results:
                match_sources_map.setdefault(doc_id, []).append("vector")

        # Merge via RRF
        docs: dict[str, RankedDoc] = {}
        for doc_id, rank in bm25_results:
            docs.setdefault(doc_id, RankedDoc(doc_id=doc_id)).bm25_rank = rank
        for doc_id, rank in vector_results:
            docs.setdefault(doc_id, RankedDoc(doc_id=doc_id)).vector_rank = rank

        ranked = sorted(docs.values(), key=lambda d: d.rrf, reverse=True)

        # Load full guardrail rows for ranked results
        results: list[SearchResult] = []
        for rd in ranked:
            row = conn.execute(
                "SELECT id, title, severity, status, guidance, scope, applies_to, "
                "lifecycle_stage, owner FROM guardrails WHERE id = ?",
                (rd.doc_id,),
            ).fetchone()
            if row is None:
                continue

            # Apply post-ranking filters
            if filters:
                if filters.get("status") and row[3] != filters["status"]:
                    continue
                if filters.get("severity") and row[2] != filters["severity"]:
                    continue
                if filters.get("scope"):
                    row_scope = orjson.loads(row[5])
                    if filters["scope"] not in row_scope:
                        continue
                if filters.get("applies_to"):
                    row_applies = orjson.loads(row[6])
                    if filters["applies_to"] not in row_applies:
                        continue
                if filters.get("lifecycle_stage"):
                    row_lc = orjson.loads(row[7])
                    if filters["lifecycle_stage"] not in row_lc:
                        continue
                if filters.get("owner") and row[8] != filters["owner"]:
                    continue

            snippet = row[4][:150] if row[4] else ""
            results.append(
                SearchResult(
                    id=row[0],
                    title=row[1],
                    severity=row[2],
                    status=row[3],
                    score=round(rd.rrf, 6),
                    match_sources=match_sources_map.get(rd.doc_id, []),
                    snippet=snippet,
                )
            )

        total = len(results)
        return results[:top], total
    finally:
        conn.close()
